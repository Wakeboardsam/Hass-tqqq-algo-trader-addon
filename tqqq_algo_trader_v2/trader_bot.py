# tqqq_algo_trader_v2/trader_bot.py
import asyncio
import os
import sqlite3
import time
import logging
import json
from dataclasses import dataclass
from typing import List, Optional
# CRITICAL FIX: Import timezone explicitly
from datetime import datetime, timedelta, timezone

# --- Timezone Support ---
try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Fallback for older Python versions
    class ZoneInfo:
        def __init__(self, key): pass
        def utcoffset(self, dt): return timedelta(hours=-7)
        def tzname(self, dt): return "MST"
        def dst(self, dt): return timedelta(0)

import yaml
from aiohttp import web

# --- IMPORT UI GENERATOR ---
from webui_assets import get_dashboard_html

# ---------- Alpaca-py Imports ----------
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# ---------- PERSISTENCE SETUP ----------
CONFIG_DIR = "/config/tqqq-bot"
if not os.path.exists(CONFIG_DIR):
    try:
        os.makedirs(CONFIG_DIR)
        print(f"Created persistent directory: {CONFIG_DIR}")
    except Exception as e:
        print(f"Could not create {CONFIG_DIR}, falling back to /data: {e}")
        CONFIG_DIR = "/data/tqqq-bot"

# ---------- Config Loading ----------
BOT_CONFIG = "/data/options.json"
LEDGER_DB = os.path.join(CONFIG_DIR, "ledger_v2.db")

cfg = {}
try:
    with open(BOT_CONFIG, 'r') as f:
        cfg = json.load(f)
        print(f"Loaded config from {BOT_CONFIG}")
except (FileNotFoundError, json.JSONDecodeError):
    try:
        with open(BOT_CONFIG, 'r') as f:
            cfg = yaml.safe_load(f)
    except Exception:
        pass

# ---------- TIMEZONE SETUP (Dynamic) ----------
TZ_STR = cfg.get("timezone", "America/Denver")
try:
    MY_TIMEZONE = ZoneInfo(TZ_STR)
except Exception:
    print(f"Invalid timezone {TZ_STR}, defaulting to UTC")
    MY_TIMEZONE = timezone.utc

def local_time(*args):
    """Helper to convert UTC to User's Configured Timezone for Logging"""
    # FIX: Use timezone.utc directly
    utc_dt = datetime.now(timezone.utc)
    my_dt = utc_dt.astimezone(MY_TIMEZONE)
    return my_dt.timetuple()

# ---------- Logging Setup ----------
LOG_FILE = os.path.join(CONFIG_DIR, "bot.log")

# Apply the dynamic timezone converter to the logger
logging.Formatter.converter = local_time

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s: %(message)s",
                    datefmt="%H:%M:%S", # Military Time
                    handlers=[logging.FileHandler(LOG_FILE),
                              logging.StreamHandler()])

logger = logging.getLogger("tqqq-bot")
logger.info(f"Timezone set to: {TZ_STR}")

# --- Environment Configuration ---
ALPACA_API_KEY = cfg.get("alpaca_api_key") or os.environ.get("ALPACA_API_KEY")
ALPACA_API_SECRET = cfg.get("alpaca_secret_key") or os.environ.get("ALPACA_SECRET_KEY")
USE_PAPER = cfg.get("use_paper", True)

SYMBOL = cfg.get("symbol", "TQQQ")
RF = float(cfg.get("reduction_factor", 0.95))
LEVELS = int(cfg.get("levels", 88))
CONFIG_INITIAL_CASH = float(cfg.get("initial_cash", 250000))

POLL_MS = int(cfg.get("poll_interval_ms", 500))
MIN_ORDER_SHARES = int(cfg.get("min_order_shares", 1))
MAX_POSITION_SHARES = int(cfg.get("max_position_shares", 200000))
WEBUI_PORT = int(cfg.get("webui_port", 8080))
LOG_TAIL = 200

logger.info(f"Configuration Loaded: Symbol={SYMBOL}, Config Cash={CONFIG_INITIAL_CASH}, RF={RF}, Levels={LEVELS}")
logger.info(f"Persistence Enabled: Database and Logs saved to {CONFIG_DIR}")

# ---------- Alpaca Client Setup ----------
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


# ---------- SQLite ledger setup ----------
conn = sqlite3.connect(LEDGER_DB, check_same_thread=False)
cur = conn.cursor()
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
    status: str

# ---------- Utility functions ----------
def tail_log(n: int = LOG_TAIL) -> str:
    try:
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()
        last_lines = lines[-n:]
        last_lines.reverse()
        return "".join(last_lines)
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

def clear_db():
    try:
        cur.executescript("""
            DROP TABLE IF EXISTS virtual_lots;
            DROP TABLE IF EXISTS orders;
            DROP TABLE IF EXISTS meta;
        """)
        conn.commit()
        logger.info("Database DROPPED via web UI (Hard Reset).")
        return True
    except Exception as e:
        logger.exception("Failed clearing database")
        return False

def write_meta(key: str, val: str):
    cur.execute("INSERT OR REPLACE INTO meta (key,val) VALUES (?,?)", (key, val))
    conn.commit()

def read_meta(key: str) -> Optional[str]:
    try:
        cur.execute("SELECT val FROM meta WHERE key=?", (key,))
        v = cur.fetchone()
        return v[0] if v else None
    except sqlite3.OperationalError:
        return None

def is_paused() -> bool:
    val = read_meta('paused')
    return val == "1"

def set_paused(val: bool):
    write_meta("paused", "1" if val else "0")

# ---------- Dynamic Cash Management ----------
def get_dynamic_initial_cash() -> float:
    val = read_meta('campaign_starting_equity')
    if val:
        return float(val)
    write_meta('campaign_starting_equity', str(CONFIG_INITIAL_CASH))
    return CONFIG_INITIAL_CASH

# ---------- P/L Tracking ----------
def get_season_stats() -> dict:
    try:
        equity = 0.0
        if api:
            acct = api.get_account()
            equity = float(acct.equity)
        start_equity = get_dynamic_initial_cash()
        last_pl = read_meta('last_season_pl')
        last_pl_val = float(last_pl) if last_pl else 0.0
        return {
            "current_equity": equity,
            "starting_equity": start_equity,
            "current_pl": equity - start_equity,
            "last_season_pl": last_pl_val
        }
    except Exception as e:
        logger.error(f"Error getting season stats: {e}")
        return {
            "current_equity": 0.0,
            "starting_equity": 0.0,
            "current_pl": 0.0,
            "last_season_pl": 0.0
        }

# ---------- Reconciliation Check ----------
def get_reconciliation_status() -> dict:
    actual_shares = get_actual_position_shares()
    assumed_shares = 0
    total_db_allocation = 0.0
    
    try:
        cur.execute("SELECT SUM(virtual_shares) FROM virtual_lots WHERE status='OPEN'")
        open_shares = cur.fetchone()[0] or 0
        
        pending_shares = 0
        if api:
            cur.execute("SELECT alpaca_order_id FROM virtual_lots WHERE status='ORDER_SENT'")
            sent_orders = cur.fetchall()
            for (oid,) in sent_orders:
                if oid:
                    try:
                        o = api.get_order_by_id(oid)
                        pending_shares += int(float(o.filled_qty))
                    except Exception:
                        pass

        assumed_shares = open_shares + pending_shares
        cur.execute("SELECT SUM(virtual_cost) FROM virtual_lots WHERE status IN ('OPEN', 'CLOSED')")
        total_db_allocation = cur.fetchone()[0] or 0
        
    except sqlite3.OperationalError:
        assumed_shares = 0
        total_db_allocation = 0.0
    
    account_cash = 0.0
    try:
        if api:
            account = api.get_account()
            account_cash = float(account.buying_power)
    except Exception:
        pass

    reconciled = (actual_shares == assumed_shares)
    
    # FIX: Use timezone.utc directly
    now_mt = datetime.now(timezone.utc).astimezone(MY_TIMEZONE)
    
    return {
        "reconciled": reconciled,
        "actual_shares": actual_shares,
        "assumed_shares": assumed_shares,
        "shares_delta": actual_shares - assumed_shares,
        "total_db_allocation": round(total_db_allocation, 2),
        "alpaca_cash": round(account_cash, 2),
        "timestamp": now_mt.strftime("%H:%M:%S")
    }

# ---------- Smart Startup Sync ----------
def sync_alpaca_state():
    if not api: return
    logger.info("--- SMART SYNC: Checking Alpaca for existing state ---")
    cur.execute("SELECT COUNT(1) FROM virtual_lots")
    if cur.fetchone()[0] > 0:
        logger.info("Database is not empty. Skipping import.")
        return

    try:
        req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[SYMBOL])
        orders = api.get_orders(req)
        if not orders:
            logger.info("No open orders found. Clean start.")
            return

        logger.info(f"Found {len(orders)} OPEN orders. Importing...")
        orders.sort(key=lambda x: float(x.limit_price) if x.limit_price else 0, reverse=True)

        for i, o in enumerate(orders):
            if o.side == OrderSide.BUY:
                qty = int(float(o.qty))
                price = float(o.limit_price) if o.limit_price else 0.0
                
                cur.execute("SELECT MAX(level) FROM virtual_lots")
                current_max = cur.fetchone()[0]
                new_level = 1 if current_max is None else current_max + 1
                
                sell_target = round(price * 1.01, 8) 
                
                logger.info(f"IMPORTING Order {o.id}: BUY {qty} @ {price}. Assigning to Level {new_level}.")
                
                cur.execute("""INSERT OR IGNORE INTO virtual_lots
                    (level, virtual_shares, virtual_cost, buy_price, sell_target, status, created_at, alpaca_order_id)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (new_level, qty, price*qty, price, sell_target, "ORDER_SENT", int(time.time()), str(o.id)))
                
                cur.execute("""INSERT INTO orders (alpaca_id, side, qty, price, status, created_at) 
                    VALUES (?,?,?,?,?,?)""",
                    (str(o.id), "buy", qty, price, "new", int(time.time())))
        conn.commit()
    except Exception as e:
        logger.error(f"Smart Sync failed: {e}")

# ---------- Reduction-factor allocation ----------
def compute_allocation_levels(anchor_price: float, current_level: int, starting_cash: float, rf: float, total_levels: int) -> tuple[int, float]:
    next_level = current_level + 1
    if next_level > total_levels:
        return 0, 0.0

    denom = (1 - (rf ** total_levels)) if rf != 1.0 else total_levels
    base_alloc_factor = (1 - rf) / denom
    alloc_cash = starting_cash * base_alloc_factor * (rf ** current_level) 
    step_down_percent = 0.01 
    buy_price = round(anchor_price * (1 - (next_level * step_down_percent)), 8)
    shares = max(MIN_ORDER_SHARES, int(alloc_cash // buy_price))
    
    return shares, buy_price

def seed_virtual_ledger_if_empty():
    cur.execute("SELECT COUNT(1) FROM virtual_lots")
    if cur.fetchone()[0] == 0:
        logger.info("Ledger is empty. Ready for initial buy sequence.")

# ---------- Alpaca helpers ----------
def get_latest_price() -> Optional[float]:
    if not data_api: return None
    try:
        req = StockLatestTradeRequest(symbol_or_symbols=[SYMBOL])
        trade = data_api.get_stock_latest_trade(req)
        return float(trade[SYMBOL].price)
    except Exception:
        pass
    try:
        req = StockBarsRequest(symbol_or_symbols=[SYMBOL], timeframe=TimeFrame.Minute, limit=1)
        bars = data_api.get_stock_bars(req)
        if bars and SYMBOL in bars and len(bars[SYMBOL]) > 0:
             return float(bars[SYMBOL][0].close)
    except Exception:
        logger.exception("Final price fetch failed")
    return None

def get_actual_position_shares() -> int:
    if not api: return 0
    try:
        p = api.get_open_position(SYMBOL)
        return int(float(p.qty))
    except Exception:
        return 0

def submit_order(side_str: str, qty: int, price: float) -> Optional[str]:
    if qty <= 0 or not api: return None
    side = OrderSide.BUY if side_str.lower() == 'buy' else OrderSide.SELL
    req = LimitOrderRequest(
        symbol=SYMBOL,
        qty=qty,
        side=side,
        limit_price=round(price, 2),
        time_in_force=TimeInForce.DAY,
        extended_hours=True
    )
    try:
        order = api.submit_order(order_data=req)
        status_str = order.status.value if hasattr(order.status, 'value') else str(order.status)
        cur.execute(
            "INSERT INTO orders (alpaca_id, side, qty, price, status, created_at) VALUES (?,?,?,?,?,?)",
            (str(order.id), side_str, qty, price, status_str, int(time.time()))
        )
        conn.commit()
        logger.info(f"Submitted LIMIT {side_str} order qty={qty} @ ${price:.2f}")
        return str(order.id)
    except Exception as e:
        logger.error(f"Order failed: {e}") 
        return None

def reconcile_orders():
    if not api: return
    try:
        cur.execute("SELECT id, alpaca_id FROM orders WHERE status NOT IN ('filled','canceled','expired')")
        rows = cur.fetchall()
        for rid, aid in rows:
            try:
                o = api.get_order_by_id(aid)
                order_status = o.status.value if hasattr(o.status, 'value') else str(o.status)
                cur.execute("UPDATE orders SET status=? WHERE id=?", (order_status, rid))

                if order_status == 'filled':
                    cur.execute("SELECT level FROM virtual_lots WHERE alpaca_order_id=?", (aid,))
                    lot_level_result = cur.fetchone()
                    lot_level = lot_level_result[0] if lot_level_result else None
                    
                    if lot_level is not None:
                        cur.execute("SELECT side FROM orders WHERE alpaca_id=?", (aid,))
                        order_side_row = cur.fetchone()
                        if order_side_row and order_side_row[0] == 'buy':
                            cur.execute("UPDATE virtual_lots SET status='OPEN' WHERE level=?", (lot_level,))
                            logger.info(f"Lot Level {lot_level} moved to OPEN (Filled).")
                        elif order_side_row and order_side_row[0] == 'sell':
                            cur.execute("UPDATE virtual_lots SET status='CLOSED' WHERE level=?", (lot_level,))
                            logger.info(f"Lot Level {lot_level} moved to CLOSED (Sold).")
            except Exception:
                pass
        conn.commit()
    except Exception:
        logger.exception("Reconcile failed")

# ---------- ANCHOR RESET LOGIC ----------
def check_anchor_reset():
    cur.execute("SELECT status FROM virtual_lots WHERE level=1")
    row = cur.fetchone()
    if not row: return

    if row[0] == 'CLOSED':
        logger.info(">>> ANCHOR (LEVEL 1) SOLD! TRIGGERING SEASON RESET <<<")
        stats = get_season_stats()
        final_pl = stats['current_pl']
        write_meta('last_season_pl', str(final_pl))
        logger.info(f"Season Ended. P/L: ${final_pl:.2f} banked.")

        if api:
            acct = api.get_account()
            new_cash = float(acct.equity)
            write_meta('campaign_starting_equity', str(new_cash))
            logger.info(f"Compounding! New Campaign Cash set to: ${new_cash:.2f}")

        cur.executescript("""
            DELETE FROM virtual_lots;
            DELETE FROM orders;
        """)
        conn.commit()
        logger.info("Grid wiped. Ready for new Anchor at ATH.")

# ---------- Core trading loop ----------
async def trading_loop():
    logger.info("Starting trading loop")
    
    try: sync_alpaca_state()
    except Exception as e: logger.error(f"Error during startup sync: {e}")

    try: seed_virtual_ledger_if_empty()
    except Exception as e: logger.critical(f"Failed to seed ledger: {e}")
        
    while True:
        try:
            reconcile_orders()
            check_anchor_reset()
            
            if is_paused():
                logger.info("Bot is paused (maintenance or mismatch). Sleeping.")
                await asyncio.sleep(POLL_MS/1000)
                continue

            price = get_latest_price()
            if price is None:
                await asyncio.sleep(POLL_MS/1000)
                continue

            reconciliation_status = get_reconciliation_status()
            if not reconciliation_status['reconciled']:
                logger.warning(f"MISMATCH: DB {reconciliation_status['assumed_shares']} != Alpaca {reconciliation_status['actual_shares']}. Paused.")
                await asyncio.sleep(POLL_MS/1000)
                continue

            actual_shares = reconciliation_status['actual_shares']
            
            # --- STARTUP LOGIC ---
            cur.execute("SELECT COUNT(1) FROM virtual_lots")
            if cur.fetchone()[0] == 0:
                logger.info("--- STARTUP: Placing Level 1 Anchor Buy ---")
                target_price = price 
                aggressive_limit_price = round(target_price * 1.005, 2)
                current_cash_basis = get_dynamic_initial_cash()
                qty, buy_price_calc = compute_allocation_levels(target_price, 0, current_cash_basis, RF, LEVELS)

                if qty > 0 and qty <= MAX_POSITION_SHARES:
                    sell_target = round(target_price * 1.01, 8) 
                    order_id = submit_order("buy", qty, aggressive_limit_price)
                    if order_id:
                        cur.execute("""INSERT OR IGNORE INTO virtual_lots
                            (level, virtual_shares, virtual_cost, buy_price, sell_target, status, created_at, alpaca_order_id)
                            VALUES (?,?,?,?,?,?,?,?)""",
                            (1, qty, target_price*qty, target_price, sell_target, "ORDER_SENT", int(time.time()), order_id))
                        conn.commit()
                logger.info(f"Anchor Buy submitted: QTY={qty} @ ${aggressive_limit_price:.2f}")
                await asyncio.sleep(POLL_MS/1000)
                continue

            # --- RUNNING LOGIC ---
            # 1. SELL logic
            cur.execute("SELECT level, virtual_shares, sell_target FROM virtual_lots WHERE status='OPEN' ORDER BY level")
            open_lots = cur.fetchall()
            for level, vshares, sell_target in open_lots:
                if price >= sell_target:
                    qty = min(int(vshares), actual_shares) 
                    if qty >= MIN_ORDER_SHARES:
                        logger.info(f"SELL TRIGGER level={level} target={sell_target} price={price}")
                        order_id = submit_order("sell", qty, sell_target)
                        if order_id:
                            cur.execute(
                                "UPDATE virtual_lots SET status='ORDER_SENT', alpaca_order_id=? WHERE level=?", 
                                (order_id, level)
                            )
                            conn.commit()

            # 2. BUY logic
            cur.execute("SELECT level, virtual_shares, buy_price FROM virtual_lots WHERE status='PENDING' ORDER BY level DESC")
            pending_rows = cur.fetchall()
            cur.execute("SELECT COUNT(1) FROM virtual_lots WHERE status='ORDER_SENT'")
            orders_sent_count = cur.fetchone()[0]
            
            if not pending_rows and orders_sent_count == 0:
                cur.execute("SELECT MAX(level) FROM virtual_lots")
                max_level = cur.fetchone()[0] or 0
                cur.execute("SELECT buy_price FROM virtual_lots WHERE level=1")
                anchor_result = cur.fetchone()
                anchor_price = anchor_result[0] if anchor_result else 0.0 
                if anchor_price > 0:
                    current_cash_basis = get_dynamic_initial_cash()
                    qty, buy_target_price = compute_allocation_levels(anchor_price, max_level, current_cash_basis, RF, LEVELS)
                    if qty > 0 and buy_target_price > 0:
                        sell_target = round(buy_target_price * 1.01, 8) 
                        cur.execute("""INSERT INTO virtual_lots
                            (level, virtual_shares, virtual_cost, buy_price, sell_target, status, created_at)
                            VALUES (?,?,?,?,?,?,?)""",
                            (max_level + 1, qty, buy_target_price*qty, buy_target_price, sell_target, "PENDING", int(time.time())))
                        conn.commit()
                        logger.info(f"Prepared next pending lot: Level {max_level + 1} @ ${buy_target_price:.2f}")

            cur.execute("SELECT level, virtual_shares, buy_price FROM virtual_lots WHERE status='PENDING' ORDER BY level DESC")
            pending_rows = cur.fetchall()
            actual_shares = reconciliation_status['actual_shares'] 
            
            for level, vshares, buy_price in pending_rows:
                if price <= buy_price:
                    if actual_shares + vshares > MAX_POSITION_SHARES: continue
                    qty = int(vshares)
                    if qty < MIN_ORDER_SHARES: continue
                    logger.info(f"BUY TRIGGER level={level} price={price}")
                    order_id = submit_order("buy", qty, buy_price)
                    if order_id:
                        cur.execute("UPDATE virtual_lots SET status='ORDER_SENT', alpaca_order_id=? WHERE level=?", (order_id, level))
                        conn.commit()
            
        except Exception:
            logger.exception("Exception in trading loop")
        await asyncio.sleep(POLL_MS/1000)

async def handle_index(request):
    price = get_latest_price()
    pos = get_actual_position_shares()
    cur.execute("SELECT level, virtual_shares, buy_price, sell_target, status, alpaca_order_id FROM virtual_lots ORDER BY level ASC")
    db_rows = cur.fetchall()
    cur.execute("SELECT SUM(virtual_cost) FROM virtual_lots WHERE status='OPEN'")
    r = cur.fetchone()
    open_cost = r[0] if r and r[0] else 0.0
    cur.execute("SELECT SUM(virtual_cost) FROM virtual_lots WHERE status='CLOSED'")
    r = cur.fetchone()
    closed_cost = r[0] if r and r[0] else 0.0
    reco_status = get_reconciliation_status()
    season_stats = get_season_stats()
    html = get_dashboard_html(SYMBOL, price, pos, open_cost, closed_cost, reco_status, db_rows, tail_log(200), is_paused(), season_stats)
    return web.Response(text=html, content_type='text/html')

async def api_clear_db(request):
    clear_db()
    raise web.HTTPFound('/')

async def api_status(request):
    price = get_latest_price()
    pos = get_actual_position_shares()
    cur.execute("SELECT COUNT(1) FROM virtual_lots WHERE status='OPEN'")
    open_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(1) FROM virtual_lots WHERE status='CLOSED'")
    closed_count = cur.fetchone()[0]
    data = {"symbol": SYMBOL, "price": price, "position_shares": pos, "open_virtual_lots": open_count, "closed_virtual_lots": closed_count, "reduction_factor": RF, "paused": is_paused()}
    return web.json_response(data)

async def api_levels(request):
    cur.execute("SELECT level, virtual_shares, virtual_cost, buy_price, sell_target, status FROM virtual_lots ORDER BY level")
    rows = cur.fetchall()
    levels = []
    for r in rows:
        levels.append({"level": r[0], "virtual_shares": r[1], "virtual_cost": r[2], "buy_price": r[3], "sell_target": r[4], "status": r[5]})
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
    app.router.add_post('/api/clear-db', api_clear_db)
    app.router.add_post('/api/pause', api_pause)
    app.router.add_post('/api/resume', api_resume)
    return app

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