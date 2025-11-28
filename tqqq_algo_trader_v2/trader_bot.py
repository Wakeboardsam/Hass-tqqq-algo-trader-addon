# tqqq_algo_trader_v2/trader_bot.py
import asyncio
import os
import sqlite3
import time
import logging
import json
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime, timedelta

import yaml
from aiohttp import web

# ---------- Alpaca-py Imports (UPDATED) ----------
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# ---------- Logging ----------
LOG_FILE = os.environ.get("LOG_FILE", "/data/tqqq-bot/bot.log")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s: %(message)s",
                    handlers=[logging.FileHandler(LOG_FILE),
                              logging.StreamHandler()])

logger = logging.getLogger("tqqq-bot")

# ---------- Config ----------
# Home Assistant Add-ons store config in /data/options.json by default
DEFAULT_CONFIG_PATH = "/data/options.json"
BOT_CONFIG = os.environ.get("BOT_CONFIG", DEFAULT_CONFIG_PATH)
LEDGER_DB = os.environ.get("LEDGER_DB", "/data/tqqq-bot/ledger_v2.db")

cfg = {}
try:
    # Try loading as JSON first (Standard Home Assistant)
    with open(BOT_CONFIG, 'r') as f:
        cfg = json.load(f)
        logger.info(f"Loaded config from {BOT_CONFIG}")
except (FileNotFoundError, json.JSONDecodeError):
    # Fallback to YAML if JSON fails (Backward compatibility/Local testing)
    try:
        with open(BOT_CONFIG, 'r') as f:
            cfg = yaml.safe_load(f)
            logger.info(f"Loaded YAML config from {BOT_CONFIG}")
    except FileNotFoundError:
        logger.error(f"Config file not found at {BOT_CONFIG}. Using script defaults.")
    except Exception:
        logger.exception("Error loading config file")

# --- Environment Configuration ---
ALPACA_API_KEY = cfg.get("alpaca_api_key") or os.environ.get("ALPACA_API_KEY")
ALPACA_API_SECRET = cfg.get("alpaca_secret_key") or os.environ.get("ALPACA_SECRET_KEY")
USE_PAPER = cfg.get("use_paper", True)

SYMBOL = cfg.get("symbol", "TQQQ")
RF = float(cfg.get("reduction_factor", 0.95))
LEVELS = int(cfg.get("levels", 88))
INITIAL_CASH = float(cfg.get("initial_cash", 250000))
POLL_MS = int(cfg.get("poll_interval_ms", 500))
MIN_ORDER_SHARES = int(cfg.get("min_order_shares", 1))
MAX_POSITION_SHARES = int(cfg.get("max_position_shares", 200000))
WEBUI_PORT = int(cfg.get("webui_port", 8080))
LOG_TAIL = 200 # Default if not in config

logger.info(f"Configuration Loaded: Symbol={SYMBOL}, Cash={INITIAL_CASH}, RF={RF}, Levels={LEVELS}")

# ---------- Alpaca Client Setup (UPDATED) ----------
api: Optional[TradingClient] = None
data_api: Optional[StockHistoricalDataClient] = None

if ALPACA_API_KEY and ALPACA_API_SECRET:
    try:
        api = TradingClient(ALPACA_API_KEY, ALPACA_API_SECRET, paper=USE_PAPER)
        data_api = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_API_SECRET)
        logger.info(f"Alpaca clients initialized (Paper: {USE_PAPER})")
    except Exception as e:
        logger.error(f"Failed to initialize Alpaca clients: {e}")
        api = None
        data_api = None
else:
    logger.warning("Alpaca credentials not found. API features disabled.")


# ---------- SQLite ledger setup (Schema Creation) ----------
conn = sqlite3.connect(LEDGER_DB, check_same_thread=False)
cur = conn.cursor()
# FIX: Schema created globally to guarantee tables exist before any function call.
cur.executescript("""
CREATE TABLE IF NOT EXISTS virtual_lots (
    level INTEGER PRIMARY KEY,
    virtual_shares INTEGER,
    virtual_cost REAL,
    buy_price REAL,
    sell_target REAL,
    status TEXT,
    created_at INTEGER,
    alpaca_order_id TEXT
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alpaca_id TEXT,
    side TEXT,
    qty INTEGER,
    price REAL,
    status TEXT,
    created_at INTEGER
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    val TEXT
);
""")
conn.commit()


@dataclass
class VirtualLot:
    level: int
    virtual_shares: int
    virtual_cost: float
    buy_price: float
    sell_target: float
    status: str  # PENDING, ORDER_SENT, OPEN, or CLOSED

# ---------- Utility functions ----------
def tail_log(n: int = LOG_TAIL) -> str:
    try:
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()
        return "".join(lines[-n:])
    except Exception:
        return ""

def clear_log():
    try:
        open(LOG_FILE, 'w').close()
        logger.info("Log cleared via web UI")
        return True
    except Exception as e:
        logger.exception("Failed clearing log")
        return False

# --- Clear Database and Schema Reset ---
def clear_db():
    try:
        # Drop tables first to force a schema recreation upon next loop start
        cur.executescript("""
            DROP TABLE IF EXISTS virtual_lots;
            DROP TABLE IF EXISTS orders;
            DROP TABLE IF EXISTS meta;
        """)
        conn.commit()
        # The next time the bot starts, the tables will be recreated by the module-level script execution.
        logger.info("Database (virtual_lots, orders, meta) DROPPED and cleared via web UI. Restart required.")
        return True
    except Exception as e:
        logger.exception("Failed clearing database")
        return False


def write_meta(key: str, val: str):
    cur.execute("INSERT OR REPLACE INTO meta (key,val) VALUES (?,?)", (key, val))
    conn.commit()

def read_meta(key: str) -> Optional[str]:
    try:
        cur.execute("SELECT val FROM meta WHERE key='paused'")
        v = cur.fetchone()
        return v[0] if v else None
    except sqlite3.OperationalError:
        # If meta table doesn't exist yet, assume not paused
        return "0" 


# --- FEATURE: Reconciliation Check (Internal Double Check) ---
def get_reconciliation_status() -> dict:
    """Compares actual shares held on Alpaca vs. the total recorded in the database."""
    
    # 1. Get Actual Shares from Alpaca
    actual_shares = get_actual_position_shares()
    
    # 2. Calculate Assumed Shares from DB (all 'OPEN' lots)
    # Safely handle missing tables in case of mid-run clear_db
    try:
        cur.execute("SELECT SUM(virtual_shares) FROM virtual_lots WHERE status='OPEN'")
        assumed_shares = cur.fetchone()[0] or 0
        
        cur.execute("SELECT SUM(virtual_cost) FROM virtual_lots WHERE status IN ('OPEN', 'CLOSED')")
        total_db_allocation = cur.fetchone()[0] or 0
    except sqlite3.OperationalError:
        assumed_shares = 0
        total_db_allocation = 0.0
    
    # 3. Get Total Cash/Buying Power (Alpaca Account)
    account_cash = 0.0
    try:
        if api:
            account = api.get_account()
            account_cash = float(account.buying_power)
    except Exception:
        logger.warning("Could not fetch Alpaca account buying power.")

    reconciled = (actual_shares == assumed_shares)
    
    return {
        "reconciled": reconciled,
        "actual_shares": actual_shares,
        "assumed_shares": assumed_shares,
        "shares_delta": actual_shares - assumed_shares,
        "total_db_allocation": round(total_db_allocation, 2),
        "alpaca_cash": round(account_cash, 2)
    }

# ---------- Reduction-factor allocation ----------
def compute_allocation_levels(anchor_price: float, current_level: int, starting_cash: float, rf: float, total_levels: int) -> tuple[int, float]:
    """Calculates the shares and price for the NEXT required level (current_level + 1)."""
    next_level = current_level + 1
    if next_level > total_levels:
        return 0, 0.0

    denom = (1 - (rf ** total_levels)) if rf != 1.0 else total_levels
    base_alloc_factor = (1 - rf) / denom
    
    # Calculate allocation for the next level's index
    alloc_cash = starting_cash * base_alloc_factor * (rf ** current_level) 
    
    # Calculate the price for the next level (1% step down based on original anchor price)
    step_down_percent = 0.01 
    buy_price = round(anchor_price * (1 - (next_level * step_down_percent)), 8)

    shares = max(MIN_ORDER_SHARES, int(alloc_cash // buy_price))
    
    return shares, buy_price

def seed_virtual_ledger_if_empty():
    """Checks if virtual_lots table has any data."""
    cur.execute("SELECT COUNT(1) FROM virtual_lots")
    if cur.fetchone()[0] == 0:
        logger.info("Ledger is empty. Ready for initial buy sequence.")
        
def load_open_virtual_lots() -> List[VirtualLot]:
    cur.execute("SELECT level, virtual_shares, virtual_cost, buy_price, sell_target, status FROM virtual_lots WHERE status='OPEN' ORDER BY level")
    return [VirtualLot(*r) for r in cur.fetchall()]

# ---------- Alpaca helpers (UPDATED for alpaca-py) ----------
def get_latest_price() -> Optional[float]:
    if not data_api:
        return None
    try:
        # Use latest trade price for accuracy
        req = StockLatestTradeRequest(symbol_or_symbols=[SYMBOL])
        trade = data_api.get_stock_latest_trade(req)
        return float(trade[SYMBOL].price)
    except Exception:
        logger.warning("Failed to fetch latest trade price. Falling back to bar close.")

    try:
        # Fallback: minute bar
        req = StockBarsRequest(
            symbol_or_symbols=[SYMBOL],
            timeframe=TimeFrame.Minute,
            limit=1
        )
        bars = data_api.get_stock_bars(req)
        if bars and SYMBOL in bars and len(bars[SYMBOL]) > 0:
             return float(bars[SYMBOL][0].close)
    except Exception:
        logger.exception("Final price fetch failed")
    return None

def get_actual_position_shares() -> int:
    if not api:
        return 0
    try:
        p = api.get_open_position(SYMBOL)
        return int(float(p.qty))
    except Exception:
        return 0

def submit_order(side_str: str, qty: int, price: float) -> Optional[str]:
    """Submits a Limit Order using the user's required Time In Force and Extended Hours."""
    if qty <= 0 or not api:
        return None
    
    side = OrderSide.BUY if side_str.lower() == 'buy' else OrderSide.SELL
    
    req = LimitOrderRequest(
        symbol=SYMBOL,
        qty=qty,
        side=side,
        limit_price=round(price, 2), # Price must be rounded for Alpaca API
        time_in_force=TimeInForce.DAY,
        extended_hours=True # User requested Extended Hours for reliable fills
    )

    try:
        order = api.submit_order(order_data=req)
        cur.execute("INSERT INTO orders (alpaca_id, side, qty, price, status, created_at) VALUES (?,?,?,?,?,?)",
                    (str(order.id), side_str, qty, price, str(order.status), int(time.time())))
        conn.commit()
        logger.info(f"Submitted LIMIT {side_str} order qty={qty} @ ${price:.2f}")
        return str(order.id)
    except Exception as e:
        logger.error(f"Order failed: {e}") 
        return None

def reconcile_orders():
    if not api:
        return
    try:
        # Check all orders not yet finalized
        cur.execute("SELECT id, alpaca_id FROM orders WHERE status NOT IN ('filled','canceled','expired')")
        rows = cur.fetchall()
        for rid, aid in rows:
            try:
                o = api.get_order_by_id(aid)
                order_status = str(o.status)

                # Find the virtual lot associated with this order ID
                cur.execute("SELECT level FROM virtual_lots WHERE alpaca_order_id=?", (aid,))
                lot_level_result = cur.fetchone()
                lot_level = lot_level_result[0] if lot_level_result else None

                # 1. Update the orders table status
                cur.execute("UPDATE orders SET status=? WHERE id=?", (order_status, rid))

                # 2. Update virtual_lots status if the order is filled
                if order_status == 'filled' and lot_level is not None:
                    cur.execute("SELECT side FROM orders WHERE alpaca_id=?", (aid,))
                    order_side = cur.fetchone()
                    
                    if order_side and order_side[0] == 'buy':
                        # If the buy order filled, the lot is now OPEN (holding)
                        cur.execute("UPDATE virtual_lots SET status='OPEN' WHERE level=?", (lot_level,))
                        logger.info(f"Lot Level {lot_level} moved to OPEN (Filled).")
                    elif order_side and order_side[0] == 'sell':
                        # If the sell order filled, the lot is now CLOSED (sold)
                        cur.execute("UPDATE virtual_lots SET status='CLOSED' WHERE level=?", (lot_level,))
                        logger.info(f"Lot Level {lot_level} moved to CLOSED (Sold).")

            except Exception:
                pass
        conn.commit()
    except Exception:
        logger.exception("Reconcile failed")

# ---------- Safety / Maintenance ----------
def is_paused() -> bool:
    try:
        cur.execute("SELECT val FROM meta WHERE key='paused'")
        v = cur.fetchone()
        return v[0] == "1" if v else False
    except sqlite3.OperationalError:
        return False

def set_paused(val: bool):
    write_meta("paused", "1" if val else "0")

# ---------- Core trading loop (UPDATED Logic) ----------
async def trading_loop():
    logger.info("Starting trading loop")
    
    # Run schema creation and check empty ledger
    try:
        seed_virtual_ledger_if_empty()
    except Exception as e:
        logger.critical(f"Failed to seed ledger: {e}")
        
    while True:
        try:
            # 3. Reconcile orders FIRST so we know which lots are now OPEN
            reconcile_orders()
            
            if is_paused():
                logger.info("Bot is paused (maintenance). Sleeping.")
                await asyncio.sleep(POLL_MS/1000)
                continue

            price = get_latest_price()
            if price is None:
                await asyncio.sleep(POLL_MS/1000)
                continue

            # Check reconciliation status before proceeding
            reconciliation_status = get_reconciliation_status()
            if not reconciliation_status['reconciled']:
                logger.warning(f"RECONCILIATION MISMATCH: DB Assumed {reconciliation_status['assumed_shares']} shares, Alpaca reports {reconciliation_status['actual_shares']} shares. Delta: {reconciliation_status['shares_delta']}. Bot action paused.")
                # Pausing action until manual review (or auto-correction logic is added later)
                await asyncio.sleep(POLL_MS/1000)
                continue


            actual_shares = reconciliation_status['actual_shares']
            
            # --- STARTUP LOGIC: Place Level 1 Anchor Buy ---
            cur.execute("SELECT COUNT(1) FROM virtual_lots")
            if cur.fetchone()[0] == 0:
                logger.info("--- STARTUP: Placing Level 1 Anchor Buy ---")
                
                target_price = price 
                
                # Aggressive Limit Price: Increase Limit Buy price slightly to guarantee execution
                aggressive_limit_price = round(target_price + 0.01, 2)
                
                # Calculate shares for Level 1 (current_level=0 in function)
                qty, buy_price_calc = compute_allocation_levels(target_price, 0, INITIAL_CASH, RF, LEVELS)

                if qty > 0 and qty <= MAX_POSITION_SHARES:
                    
                    sell_target = round(target_price * 1.01, 8) 
                    
                    # Submit the limit order at the AGGRESSIVE PRICE
                    order_id = submit_order("buy", qty, aggressive_limit_price)
                    
                    if order_id:
                        # Mark this lot as ORDER_SENT (Order placed, waiting for fill)
                        cur.execute("""INSERT OR IGNORE INTO virtual_lots
                            (level, virtual_shares, virtual_cost, buy_price, sell_target, status, created_at, alpaca_order_id)
                            VALUES (?,?,?,?,?,?,?,?)""",
                            (1, qty, target_price*qty, target_price, sell_target, "ORDER_SENT", int(time.time()), order_id))
                        conn.commit()
                
                logger.info(f"Anchor Buy submitted: QTY={qty} @ ${aggressive_limit_price:.2f} (Aggressive Limit). Strategy is now PENDING fill.")
                await asyncio.sleep(POLL_MS/1000)
                continue
            # --- END STARTUP LOGIC ---

            # --- RUNNING LOGIC ---
            
            # 1. SELL logic: Check all lots currently held ('OPEN')
            cur.execute("SELECT level, virtual_shares, sell_target FROM virtual_lots WHERE status='OPEN' ORDER BY level")
            open_lots = cur.fetchall()
            
            for level, vshares, sell_target in open_lots:
                if price >= sell_target:
                    qty = min(int(vshares), actual_shares) 
                    
                    if qty >= MIN_ORDER_SHARES:
                        logger.info("SELL TRIGGER level=%s sell_target=%s price=%s qty=%s", level, sell_target, price, qty)
                        
                        # Submit a LIMIT sell order at the target price
                        order_id = submit_order("sell", qty, sell_target)
                        if order_id:
                            # Mark as ORDER_SENT (waiting for fill)
                            cur.execute("UPDATE virtual_lots SET status='ORDER_SENT', alpaca_order_id=? WHERE level=?", (order_id, level))
                            conn.commit()

            # 2. BUY logic: Check all lots waiting to be bought ('PENDING')
            cur.execute("SELECT level, virtual_shares, buy_price FROM virtual_lots WHERE status='PENDING' ORDER BY level DESC")
            pending_rows = cur.fetchall()
            
            
            # If no PENDING lots exist, and no lots are ORDER_SENT, calculate and create the next PENDING lot (Level N+1)
            cur.execute("SELECT COUNT(1) FROM virtual_lots WHERE status='ORDER_SENT'")
            orders_sent_count = cur.fetchone()[0]
            
            if not pending_rows and orders_sent_count == 0:
                
                cur.execute("SELECT MAX(level) FROM virtual_lots")
                max_level = cur.fetchone()[0] or 0
                
                cur.execute("SELECT buy_price FROM virtual_lots WHERE level=1")
                anchor_result = cur.fetchone()
                anchor_price = anchor_result[0] if anchor_result else 0.0 
                
                if anchor_price > 0:
                    qty, buy_target_price = compute_allocation_levels(anchor_price, max_level, INITIAL_CASH, RF, LEVELS)

                    if qty > 0 and buy_target_price > 0:
                        
                        sell_target = round(buy_target_price * 1.01, 8) 
                        
                        cur.execute("""INSERT INTO virtual_lots
                            (level, virtual_shares, virtual_cost, buy_price, sell_target, status, created_at)
                            VALUES (?,?,?,?,?,?,?)""",
                            (max_level + 1, qty, buy_target_price*qty, buy_target_price, sell_target, "PENDING", int(time.time())))
                        conn.commit()
                        
                        logger.info(f"Prepared next pending lot: Level {max_level + 1} @ ${buy_target_price:.2f}")

            # Re-fetch PENDING rows now that the new one might be created
            cur.execute("SELECT level, virtual_shares, buy_price FROM virtual_lots WHERE status='PENDING' ORDER BY level DESC")
            pending_rows = cur.fetchall()

            actual_shares = reconciliation_status['actual_shares'] 
            
            for level, vshares, buy_price in pending_rows:
                # We only place a buy order IF the current price is at or below the target price 
                if price <= buy_price:
                    if actual_shares + vshares > MAX_POSITION_SHARES:
                        logger.info("Safety cap would be exceeded; skipping buy for level %s", level)
                        continue
                        
                    qty = int(vshares)
                    if qty < MIN_ORDER_SHARES:
                        continue
                        
                    logger.info("BUY TRIGGER level=%s buy_price=%s price=%s qty=%s", level, buy_price, price, qty)
                    
                    order_id = submit_order("buy", qty, buy_price)
                    if order_id:
                        # CRITICAL: Move lot to ORDER_SENT status immediately to prevent duplicate orders
                        cur.execute("UPDATE virtual_lots SET status='ORDER_SENT', alpaca_order_id=? WHERE level=?", (order_id, level))
                        conn.commit()
            
        except Exception:
            logger.exception("Exception in trading loop")
            
        await asyncio.sleep(POLL_MS/1000)

# ---------- Web UI (aiohttp) ----------
async def handle_index(request):
    price = get_latest_price()
    pos = get_actual_position_shares()
    cur.execute("SELECT SUM(virtual_cost) FROM virtual_lots WHERE status='OPEN'")
    r = cur.fetchone()
    open_cost = r[0] if r and r[0] else 0.0
    
    cur.execute("SELECT SUM(virtual_cost) FROM virtual_lots WHERE status='CLOSED'")
    r = cur.fetchone()
    closed_cost = r[0] if r and r[0] else 0.0
    
    # Get Reconciliation Status
    reco_status = get_reconciliation_status()
    reco_alert = ""
    if not reco_status['reconciled']:
        reco_alert = f"""<p style='color:red; font-weight:bold;'>WARNING: Share Mismatch! DB ({reco_status['assumed_shares']}) != Alpaca ({reco_status['actual_shares']})</p>"""
    
    html = f"""
    <html>
    <head><title>TQQQ Bot Status</title></head>
    <body>
      <h2>TQQQ Bot Status</h2>
      {reco_alert}
      <p>Symbol: {SYMBOL}</p>
      <p>Current Price: {price}</p>
      <p>Actual Position Shares (Alpaca): {pos}</p>
      <p>Open Virtual Cost (sum): {open_cost:.2f}</p>
      <p>Closed Virtual Cost (sum): {closed_cost:.2f}</p>
      <p>Reduction Factor: {RF}</p>
      <p>Levels configured: {LEVELS}</p>
      <p>Initial Cash: ${INITIAL_CASH}</p>
      <p><a href="/api/levels">View full levels (JSON)</a></p>
      
      <form method="post" action="/api/clear-logs" style="display:inline;"><button type="submit">Clear Logs</button></form>
      <form method="post" action="/api/clear-db" style="display:inline;"><button type="submit">Clear Database (DANGER!)</button></form>
      <form method="post" action="/api/pause" style="display:inline;"><button type="submit">Pause Bot</button></form>
      <form method="post" action="/api/resume" style="display:inline;"><button type="submit">Resume Bot</button></form>
      
      <h3>Reconciliation Data</h3>
      <ul>
        <li>Shares Delta (Actual - Assumed): {reco_status['shares_delta']}</li>
        <li>Account Buying Power: ${reco_status['alpaca_cash']:.2f}</li>
      </ul>
      
      <h3>Recent logs</h3>
      <pre>{tail_log(200)}</pre>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')

# --- NEW API Endpoint: Clear Database ---
async def api_clear_db(request):
    clear_db()
    raise web.HTTPFound('/')
# --- END NEW API Endpoint ---

async def api_status(request):
    price = get_latest_price()
    pos = get_actual_position_shares()
    cur.execute("SELECT COUNT(1) FROM virtual_lots WHERE status='OPEN'")
    open_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(1) FROM virtual_lots WHERE status='CLOSED'")
    closed_count = cur.fetchone()[0]
    data = {
        "symbol": SYMBOL,
        "price": price,
        "position_shares": pos,
        "open_virtual_lots": open_count,
        "closed_virtual_lots": closed_count,
        "reduction_factor": RF,
        "paused": is_paused()
    }
    return web.json_response(data)

async def api_levels(request):
    cur.execute("SELECT level, virtual_shares, virtual_cost, buy_price, sell_target, status FROM virtual_lots ORDER BY level")
    rows = cur.fetchall()
    levels = []
    for r in rows:
        levels.append({
            "level": r[0],
            "virtual_shares": r[1],
            "virtual_cost": r[2],
            "buy_price": r[3],
            "sell_target": r[4],
            "status": r[5]
        })
    return web.json_response({"levels": levels})

async def api_logs(request):
    return web.Response(text=tail_log(LOG_TAIL), content_type='text/plain')

async def api_clear_logs(request):
    clear_log()
    raise web.HTTPFound('/')

async def api_pause(request):
    set_paused(True)
    raise web.HTTPFound('/')

async def api_resume(request):
    set_paused(False)
    raise web.HTTPFound('/')

def create_web_app():
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/api/status', api_status)
    app.router.add_get('/api/levels', api_levels)
    app.router.add_post('/api/clear-logs', api_clear_logs)
    app.router.add_post('/api/clear-db', api_clear_db) # New routing endpoint
    app.router.add_post('/api/pause', api_pause)
    app.router.add_post('/api/resume', api_resume)
    return app

# ---------- Main ----------
async def main():
    logger.info("Starting TQQQ bot v2 (alpaca-py)")
    
    loop = asyncio.get_event_loop()
    app = create_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', WEBUI_PORT)
    await site.start()
    logger.info(f"Web UI listening on port {WEBUI_PORT}")

    await trading_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down bot")
