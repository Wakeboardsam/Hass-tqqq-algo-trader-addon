# tqqq_bot_tester/bot_tester.py
import asyncio
import os
import sqlite3
import time
import logging
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# --- Timezone Support ---
try:
    from zoneinfo import ZoneInfo
except ImportError:
    class ZoneInfo:
        def __init__(self, key): pass
        def utcoffset(self, dt): return timedelta(hours=-7)
        def tzname(self, dt): return "MST"
        def dst(self, dt): return timedelta(0)

import yaml
from aiohttp import web
from webui_assets import get_dashboard_html

# ---------- SIMULATION PERSISTENCE ----------
# ISOLATED FOLDER: /config/tqqq-bot-tester
CONFIG_DIR = "/config/tqqq-bot-tester"
if not os.path.exists(CONFIG_DIR):
    try:
        os.makedirs(CONFIG_DIR)
        print(f"Created tester directory: {CONFIG_DIR}")
    except Exception as e:
        print(f"Could not create {CONFIG_DIR}, fallback to /data: {e}")
        CONFIG_DIR = "/data"

# ---------- Logging ----------
LOG_FILE = os.path.join(CONFIG_DIR, "tester.log")
logger = logging.getLogger("tqqq-tester")

# ---------- Config ----------
BOT_CONFIG = "/data/options.json"
LEDGER_DB = os.path.join(CONFIG_DIR, "tester_ledger.db")

# Global Config Cache
sim_config = {}

def reload_config():
    """Reads config every loop to catch manual price changes from the UI."""
    global sim_config
    try:
        with open(BOT_CONFIG, 'r') as f:
            sim_config = json.load(f)
    except Exception:
        pass # Keep old config if read fails

# Initial Load
reload_config()

# Timezone Setup
TZ_STR = sim_config.get("timezone", "America/Denver")
try:
    MY_TIMEZONE = ZoneInfo(TZ_STR)
except:
    MY_TIMEZONE = timezone.utc

def local_time(*args):
    utc_dt = datetime.now(timezone.utc)
    my_dt = utc_dt.astimezone(MY_TIMEZONE)
    return my_dt.timetuple()

logging.Formatter.converter = local_time
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S",
                    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])

logger.info(f"--- STARTING SIMULATION BOT ---")
logger.info(f"Timezone: {TZ_STR}")
logger.info(f"Persistence: {CONFIG_DIR}")

# ---------- SIMULATION STATE ----------
# Since we don't have Alpaca, we track "Account" in memory or DB.
# For simplicity, we calculate Equity = Cash + (Shares * SimPrice)
# We store "Simulated Cash" in the Meta table.

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

# ---------- Helper Functions ----------
def tail_log(n=200):
    try:
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()
        last = lines[-n:]
        last.reverse()
        return "".join(last)
    except: return ""

def clear_db():
    cur.executescript("""
        DROP TABLE IF EXISTS virtual_lots;
        DROP TABLE IF EXISTS orders;
        DROP TABLE IF EXISTS meta;
    """)
    conn.commit()
    logger.info("SIMULATION RESET. Database wiped.")

def write_meta(key, val):
    cur.execute("INSERT OR REPLACE INTO meta (key,val) VALUES (?,?)", (key, str(val)))
    conn.commit()

def read_meta(key):
    cur.execute("SELECT val FROM meta WHERE key=?", (key,))
    r = cur.fetchone()
    return r[0] if r else None

# ---------- SIMULATION LOGIC ----------

def get_sim_price():
    """Reads the 'manual_market_price' from the config tab."""
    reload_config()
    return float(sim_config.get("manual_market_price", 100.00))

def get_sim_cash():
    """Gets simulated cash on hand."""
    c = read_meta('sim_cash')
    if c is None:
        # Initialize with config cash
        start = float(sim_config.get("initial_cash", 100000))
        write_meta('sim_cash', start)
        return start
    return float(c)

def update_sim_cash(amount_change):
    curr = get_sim_cash()
    new_val = curr + amount_change
    write_meta('sim_cash', new_val)
    return new_val

def get_sim_shares():
    """Calculates total shares held based on OPEN lots in DB."""
    # In simulation, we trust the DB 100% because there is no external broker.
    cur.execute("SELECT SUM(virtual_shares) FROM virtual_lots WHERE status='OPEN'")
    return cur.fetchone()[0] or 0

def submit_sim_order(side, qty, price):
    """Creates a 'Pending' order in the database."""
    sim_id = f"SIM-{uuid.uuid4().hex[:8]}"
    logger.info(f"SIMULATED ORDER: {side.upper()} {qty} @ ${price:.2f} (ID: {sim_id})")
    
    # Record the order
    cur.execute("INSERT INTO orders (alpaca_id, side, qty, price, status, created_at) VALUES (?,?,?,?,?,?)",
                (sim_id, side, qty, price, "new", int(time.time())))
    conn.commit()
    return sim_id

def match_engine():
    """
    The Heart of the Simulator.
    Checks open orders against the Manual Market Price.
    If price crosses limit, FILLS the order.
    """
    current_price = get_sim_price()
    
    # 1. Get all pending orders
    cur.execute("SELECT id, alpaca_id, side, qty, price FROM orders WHERE status='new'")
    pending_orders = cur.fetchall()
    
    for row in pending_orders:
        oid, alpaca_id, side, qty, limit_price = row
        filled = False
        
        if side == 'buy' and current_price <= limit_price:
            # Price dropped enough to buy
            filled = True
            cost = qty * limit_price
            update_sim_cash(-cost) # Spend Cash
            logger.info(f"⚡ SIM FILL: BOUGHT {qty} @ ${limit_price:.2f} (Market: ${current_price})")
            
        elif side == 'sell' and current_price >= limit_price:
            # Price rose enough to sell
            filled = True
            proceeds = qty * limit_price
            update_sim_cash(proceeds) # Receive Cash
            logger.info(f"⚡ SIM FILL: SOLD {qty} @ ${limit_price:.2f} (Market: ${current_price})")
            
        if filled:
            # Update Order Table
            cur.execute("UPDATE orders SET status='filled' WHERE id=?", (oid,))
            
            # Update Virtual Lots Table
            if side == 'buy':
                # Find the lot waiting for this order
                cur.execute("UPDATE virtual_lots SET status='OPEN' WHERE alpaca_order_id=?", (alpaca_id,))
            elif side == 'sell':
                cur.execute("UPDATE virtual_lots SET status='CLOSED' WHERE alpaca_order_id=?", (alpaca_id,))
            
            conn.commit()

# ---------- STANDARD BOT LOGIC (Adapted for Sim) ----------

def compute_allocation_levels(anchor_price, current_level, starting_cash, rf, total_levels):
    # Same math as production
    next_level = current_level + 1
    if next_level > total_levels: return 0, 0.0
    denom = (1 - (rf ** total_levels)) if rf != 1.0 else total_levels
    base_alloc_factor = (1 - rf) / denom
    alloc_cash = starting_cash * base_alloc_factor * (rf ** current_level) 
    step_down_percent = 0.01 
    buy_price = round(anchor_price * (1 - (next_level * step_down_percent)), 2)
    shares = max(1, int(alloc_cash // buy_price))
    return shares, buy_price

async def simulation_loop():
    logger.info("Simulation Loop Started. Change 'manual_market_price' in Config to move market.")
    
    while True:
        try:
            # 1. Refresh Config (Price)
            reload_config()
            price = get_sim_price()
            
            # 2. Run Match Engine (Check if orders fill)
            match_engine()
            
            # 3. Check Anchor Reset (Season logic)
            cur.execute("SELECT status FROM virtual_lots WHERE level=1")
            row = cur.fetchone()
            if row and row[0] == 'CLOSED':
                logger.info(">>> SIMULATION: ANCHOR SOLD! RESETTING SEASON <<<")
                # Reset DB but keep cash
                cur.executescript("DELETE FROM virtual_lots; DELETE FROM orders;")
                conn.commit()
                # Update starting equity for next season
                current_equity = get_sim_cash() # shares are 0, so equity = cash
                write_meta('campaign_starting_equity', current_equity)

            # 4. Trading Logic
            # Get Start Cash
            start_cash_val = read_meta('campaign_starting_equity')
            if not start_cash_val:
                start_cash_val = sim_config.get("initial_cash", 100000)
                write_meta('campaign_starting_equity', start_cash_val)
            start_cash = float(start_cash_val)
            
            # STARTUP
            cur.execute("SELECT COUNT(1) FROM virtual_lots")
            if cur.fetchone()[0] == 0:
                logger.info(f"--- SIM STARTUP: Placing Anchor Buy at ${price} ---")
                target = price
                limit = round(target * 1.005, 2)
                qty, _ = compute_allocation_levels(target, 0, start_cash, sim_config['reduction_factor'], sim_config['levels'])
                
                oid = submit_sim_order("buy", qty, limit)
                sell_target = round(limit * 1.01, 2)
                
                cur.execute("""INSERT INTO virtual_lots (level, virtual_shares, virtual_cost, buy_price, sell_target, status, created_at, alpaca_order_id)
                               VALUES (?,?,?,?,?,?,?,?)""",
                               (1, qty, limit*qty, limit, sell_target, "ORDER_SENT", int(time.time()), oid))
                conn.commit()
                
            # RUNNING
            # Sell Logic
            cur.execute("SELECT level, virtual_shares, sell_target FROM virtual_lots WHERE status='OPEN'")
            for lvl, qty, target in cur.fetchall():
                if price >= target:
                    logger.info(f"SIM TRIGGER: Selling Level {lvl}")
                    oid = submit_sim_order("sell", qty, target)
                    cur.execute("UPDATE virtual_lots SET status='ORDER_SENT', alpaca_order_id=? WHERE level=?", (oid, lvl))
                    conn.commit()

            # Buy Logic
            cur.execute("SELECT level, virtual_shares, buy_price FROM virtual_lots WHERE status='PENDING' ORDER BY level DESC")
            pending = cur.fetchall()
            
            # Check if we need to generate next pending level
            cur.execute("SELECT COUNT(1) FROM virtual_lots WHERE status='ORDER_SENT'")
            if not pending and cur.fetchone()[0] == 0:
                cur.execute("SELECT MAX(level), buy_price FROM virtual_lots WHERE level=1")
                # Need Anchor Price to calculate next level
                anchor_row = cur.fetchone() # This query is wrong, let's fix
                
                cur.execute("SELECT buy_price FROM virtual_lots WHERE level=1")
                ar = cur.fetchone()
                cur.execute("SELECT MAX(level) FROM virtual_lots")
                mr = cur.fetchone()
                
                if ar and mr:
                    anchor_price = ar[0]
                    max_lvl = mr[0]
                    qty, buy_target = compute_allocation_levels(anchor_price, max_lvl, start_cash, sim_config['reduction_factor'], sim_config['levels'])
                    if qty > 0:
                        sell_target = round(buy_target * 1.01, 2)
                        cur.execute("INSERT INTO virtual_lots (level, virtual_shares, virtual_cost, buy_price, sell_target, status, created_at) VALUES (?,?,?,?,?,?,?)",
                                    (max_lvl+1, qty, buy_target*qty, buy_target, sell_target, "PENDING", int(time.time())))
                        conn.commit()
                        logger.info(f"Generated Plan for Level {max_lvl+1} @ ${buy_target}")

            # Execute Buys
            cur.execute("SELECT level, virtual_shares, buy_price FROM virtual_lots WHERE status='PENDING'")
            for lvl, qty, target in cur.fetchall():
                if price <= target:
                    logger.info(f"SIM TRIGGER: Buying Level {lvl}")
                    oid = submit_sim_order("buy", qty, target)
                    cur.execute("UPDATE virtual_lots SET status='ORDER_SENT', alpaca_order_id=? WHERE level=?", (oid, lvl))
                    conn.commit()

        except Exception:
            logger.exception("Sim Loop Error")
        
        await asyncio.sleep(1) # Check every second

# ---------- Web App ----------
async def handle_index(request):
    reload_config()
    price = get_sim_price()
    shares = get_sim_shares()
    cash = get_sim_cash()
    equity = cash + (shares * price)
    
    cur.execute("SELECT level, virtual_shares, buy_price, sell_target, status, alpaca_order_id FROM virtual_lots ORDER BY level ASC")
    rows = cur.fetchall()
    
    start_equity = float(read_meta('campaign_starting_equity') or sim_config.get("initial_cash", 100000))
    season_stats = {
        "current_equity": equity,
        "starting_equity": start_equity,
        "current_pl": equity - start_equity,
        "last_season_pl": 0.0 # TODO: Store this on reset
    }
    
    reco = {
        "reconciled": True, # Always true in sim
        "assumed_shares": shares,
        "actual_shares": shares,
        "alpaca_cash": cash,
        "timestamp": datetime.now(timezone.utc).astimezone(MY_TIMEZONE).strftime("%H:%M:%S")
    }
    
    html = get_dashboard_html(
        sim_config.get("symbol", "SIM"), price, shares, 0, 0, reco, rows, tail_log(), False, season_stats
    )
    return web.Response(text=html, content_type='text/html')

async def api_clear_db(request):
    clear_db()
    raise web.HTTPFound('/')

def create_app():
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_post('/api/clear-db', api_clear_db)
    return app

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = create_app()
    runner = web.AppRunner(app)
    loop.run_until_complete(runner.setup())
    port = sim_config.get("webui_port", 8081)
    site = web.TCPSite(runner, '0.0.0.0', port)
    loop.run_until_complete(site.start())
    logger.info(f"Sim Web UI on port {port}")
    loop.run_until_complete(simulation_loop())
