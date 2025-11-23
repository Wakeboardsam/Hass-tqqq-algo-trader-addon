# trader_bot.py
import time
import os
import pandas as pd
from math import floor
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest, TakeProfitRequest
from alpaca.trading.enums import OrderSide, OrderClass, TimeInForce, OrderStatus
from alpaca.data.requests import StockLatestQuoteRequest, StockLatestTradeRequest
from alpaca.data.historical import StockHistoricalDataClient
import logging 

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration & Constants ---
API_KEY = os.environ.get("ALPACA_API_KEY_ID")
SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")

if not API_KEY or not SECRET_KEY:
    logger.error("FATAL ERROR: API keys not found in environment variables. Exiting.")
    exit(1)

SYMBOL = "TQQQ"
LEDGER_FILE = "/config/tqqq_ledger.csv"
POLL_INTERVAL_SEC = 15 
TOTAL_LEVELS = 88

# Strategy Parameters
REDUCTION_FACTOR = 0.95
STARTING_CASH = 250000.00
PROFIT_TARGET_PERCENT = 0.0100

# --- Alpaca Clients ---
trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True) 
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

# --- 1. Ledger Management ---

def load_ledger() -> pd.DataFrame:
    """Loads the lot ledger from a persistent CSV file."""
    if os.path.exists(LEDGER_FILE):
        return pd.read_csv(LEDGER_FILE)
    
    return pd.DataFrame({
        'lot_id': pd.Series(dtype='str'),
        'purchase_price': pd.Series(dtype='float'),
        'shares': pd.Series(dtype='int'),
        'target_sell_price': pd.Series(dtype='float'),
        'alpaca_order_id': pd.Series(dtype='str'),
        'is_open': pd.Series(dtype='bool'),
        'level': pd.Series(dtype='int')
    })

def save_ledger(ledger_df: pd.DataFrame):
    """Saves the current lot ledger to CSV."""
    ledger_df.to_csv(LEDGER_FILE, index=False)
    logger.info(f"Ledger saved with {len(ledger_df[ledger_df['is_open']])} open lots.")


# --- 2. Trading Functions (Core Logic) ---

def calculate_shares_to_buy(
    starting_cash: float, 
    reduction_factor: float, 
    lots_held_before: int, 
    current_price: float
) -> int:
    """Calculates the share quantity for the next purchase."""
    if lots_held_before >= TOTAL_LEVELS:
        return 0

    multiplier = (1 - reduction_factor) / (1 - (reduction_factor ** TOTAL_LEVELS))
    reduction_scaling = reduction_factor ** lots_held_before
    cash_to_invest = starting_cash * multiplier * reduction_scaling
    
    shares_to_buy = floor(cash_to_invest / current_price)
    
    return max(0, shares_to_buy) 

def submit_bracket_order(
    qty_to_buy: int, 
    entry_price: float, 
    take_profit_price: float,
    lot_id: str
) -> str | None:
    """Submits a GTC Limit Buy order with an attached Take-Profit Sell limit order."""
    
    take_profit_request = TakeProfitRequest(
        limit_price=round(take_profit_price, 2)
    )

    bracket_order_data = LimitOrderRequest(
        symbol=SYMBOL,
        qty=qty_to_buy,
        side=OrderSide.BUY,
        limit_price=round(entry_price, 2),
        time_in_force=TimeInForce.GTC,
        order_class=OrderClass.BRACKET,
        take_profit=take_profit_request,
        client_order_id=lot_id
    )

    try:
        order = trading_client.submit_order(order_data=bracket_order_data)
        logger.info(f"Submitted Bracket Order | Lot ID: {lot_id} | Entry: ${entry_price:.2f}")
        return order.id
    except Exception as e:
        logger.error(f"Error submitting bracket order for {lot_id}: {e}")
        return None

# --- 3. Polling and Market Status ---

def fetch_tqqq_price() -> float | None:
    """Uses API polling to get the latest ASK price for TQQQ."""
    try:
        quote_request = StockLatestQuoteRequest(symbol_or_symbols=SYMBOL)
        quote = data_client.get_stock_latest_quote(quote_request)

        ask_price = quote[SYMBOL].ask_price
        
        if ask_price > 0:
            return ask_price
        
        # Fallback to the last trade price if ask is zero
        trade_request = StockLatestTradeRequest(symbol_or_symbols=SYMBOL)
        last_trade = data_client.get_stock_latest_trade(trade_request)
        return last_trade[SYMBOL].price if last_trade[SYMBOL].price > 0 else None
        
    except Exception as e:
        logger.error(f"Error fetching price: {e}")
        return None

def is_market_open() -> bool:
    """Checks if the market is currently open."""
    try:
        clock = trading_client.get_clock()
        return clock.is_open
    except Exception as e:
        logger.error(f"Error checking market clock: {e}")
        return True 

# --- 4. Reconciliation and Decision Logic ---

def reconciliation_check(ledger_df: pd.DataFrame) -> pd.DataFrame:
    """Checks for filled orders on Alpaca and updates the ledger."""
    if ledger_df.empty:
        return ledger_df

    closed_orders = trading_client.get_orders(status=OrderStatus.CLOSED, nested=True)
    
    return ledger_df

def trading_logic(ledger_df: pd.DataFrame, current_price: float, starting_cash: float) -> pd.DataFrame:
    """Determines if a new buy order should be placed."""

    open_lots = ledger_df[ledger_df['is_open']]
    
    # --- 1. INITIAL BUY CHECK ---
    if open_lots.empty:
        logger.info("Ledger is empty. Attempting initial buy sequence.")
        
        latest_purchase_price = current_price
        shares = calculate_shares_to_buy(starting_cash, REDUCTION_FACTOR, 0, latest_purchase_price)
        
        if shares > 0:
            target_sell_price = latest_purchase_price * (1 + PROFIT_TARGET_PERCENT)
            lot_id = f"TQQQ_L0_RF{str(REDUCTION_FACTOR).replace('.', '')}_{int(time.time())}"
            
            order_id = submit_bracket_order(shares, latest_purchase_price, target_sell_price, lot_id)
            
            if order_id:
                new_row = pd.DataFrame([{
                    'lot_id': lot_id,
                    'purchase_price': latest_purchase_price,
                    'shares': shares,
                    'target_sell_price': target_sell_price,
                    'alpaca_order_id': order_id,
                    'is_open': True,
                    'level': 0
                }])
                ledger_df = pd.concat([ledger_df, new_row], ignore_index=True)
                logger.info(f"Initial Lot L0 submitted: {shares} shares @ ${latest_purchase_price:.2f}")
        
    # --- 2. GRID ENTRY CHECK ---
    else:
        deepest_level = open_lots['level'].max()
        anchor_lot = ledger_df[ledger_df['level'] == 0].iloc[0]
        anchor_price = anchor_lot['purchase_price']
        next_buy_level = deepest_level + 1
        next_buy_price_target = anchor_price * (1 - (next_buy_level * PROFIT_TARGET_PERCENT))
        
        if current_price <= next_buy_price_target and next_buy_level < TOTAL_LEVELS:
            logger.info(f"Price dropped to level {next_buy_level}. Submitting next grid buy.")
            
            shares = calculate_shares_to_buy(starting_cash, REDUCTION_FACTOR, next_buy_level, next_buy_price_target)

            if shares > 0:
                target_sell_price = anchor_price * (1 - ((next_buy_level - 1) * PROFIT_TARGET_PERCENT))
                lot_id = f"TQQQ_L{next_buy_level}_RF{str(REDUCTION_FACTOR).replace('.', '')}_{int(time.time())}"
                
                order_id = submit_bracket_order(shares, next_buy_price_target, target_sell_price, lot_id)
                
                if order_id:
                    new_row = pd.DataFrame([{
                        'lot_id': lot_id,
                        'purchase_price': next_buy_price_target,
                        'shares': shares,
                        'target_sell_price': target_sell_price,
                        'alpaca_order_id': order_id,
                        'is_open': True,
                        'level': next_buy_level
                    }])
                    ledger_df = pd.concat([ledger_df, new_row], ignore_index=True)
                    logger.info(f"Grid Buy L{next_buy_level} submitted: {shares} shares @ ${next_buy_price_target:.2f}")

    return ledger_df


# --- 5. Main Execution Loop ---

def main():
    """The main execution loop for the trading bot."""
    logger.info("--- Starting TQQQ Algo Trader (Paper Mode) ---")
    
    ledger_df = load_ledger()
    
    while True:
        try:
            if not is_market_open():
                logger.info("Market closed. Sleeping for 1 hour.")
                time.sleep(3600)
                continue
            
            current_price = fetch_tqqq_price()
            if not current_price:
                logger.warning("Failed to fetch price. Skipping cycle.")
                time.sleep(POLL_INTERVAL_SEC)
                continue
            
            logger.info(f"--- Cycle Start | Price: ${current_price:.2f} ---")

            ledger_df = reconciliation_check(ledger_df)
            ledger_df = trading_logic(ledger_df, current_price, STARTING_CASH)
            save_ledger(ledger_df)
            
            time.sleep(POLL_INTERVAL_SEC)

        except KeyboardInterrupt:
            logger.info("\nShutting down bot via manual interrupt...")
            break
        except Exception as e:
            logger.error(f"CRITICAL ERROR in main loop: {e}", exc_info=True)
            time.sleep(60)

if __name__ == '__main__':
    main()
