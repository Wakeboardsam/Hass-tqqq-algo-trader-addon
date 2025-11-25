# tqqq_algo_trader_v2/trader_bot.py
import asyncio
import os
import sqlite3
import time
import logging
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional

import yaml
from aiohttp import web
from alpaca_trade_api import REST

# ---------- Logging ----------
LOG_FILE = os.environ.get("LOG_FILE", "/data/tqqq-bot/bot.log")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s: %(message)s",
                    handlers=[logging.FileHandler(LOG_FILE),
                              logging.StreamHandler()])

logger = logging.getLogger("tqqq-bot")

# ---------- Config ----------
BOT_CONFIG = os.environ.get("BOT_CONFIG", "/data/tqqq-bot/config.yaml")
LEDGER_DB = os.environ.get("LEDGER_DB", "/data/tqqq-bot/ledger_v2.db")

with open(BOT_CONFIG, 'r') as f:
    cfg = yaml.safe_load(f)

ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY", cfg.get("alpaca", {}).get("api_key", ""))
ALPACA_API_SECRET = os.environ.get("ALPACA_API_SECRET", cfg.get("alpaca", {}).get("api_secret", ""))
USE_PAPER = cfg.get("alpaca", {}).get("use_paper", True)
ALPACA_BASE = cfg.get("alpaca", {}).get("base_url", "https://paper-api.alpaca.markets")

SYMBOL = cfg.get("symbol", "TQQQ")
RF = float(cfg.get("reduction_factor", 0.95))
LEVELS = int(cfg.get("levels", 88))
INITIAL_CASH = float(cfg.get("initial_cash", 250000))
INITIAL_PRICE = float(cfg.get("initial_price", 0.0))
POLL_MS = int(cfg.get("poll_interval_ms", 500))
MIN_ORDER_SHARES = int(cfg.get("min_order_shares", 1))
MAX_POSITION_SHARES = int(cfg.get("max_position_shares", 200000))
WEBUI_PORT = int(cfg.get("webui", {}).get("port", 8080))
LOG_TAIL = int(cfg.get("log_tail_lines", 200))

# Alpaca REST client
if ALPACA_API_KEY and ALPACA_API_SECRET:
    api = REST(ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_BASE, api_version='v2')
else:
    api = None

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
    created_at INTEGER
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
    status: str  # OPEN or CLOSED

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

def write_meta(key: str, val: str):
    cur.execute("INSERT OR REPLACE INTO meta (key,val) VALUES (?,?)", (key, val))
    conn.commit()

def read_meta(key: str) -> Optional[str]:
    cur.execute("SELECT val FROM meta WHERE key=?", (key,))
    r = cur.fetchone()
    return r[0] if r else None

# ---------- Reduction-factor allocation ----------
def compute_allocation_levels(initial_price: float, starting_cash: float, rf: float, levels: int):
    step = round(initial_price * 0.01, 8)  # 1% step based on initial price
    denom = (1 - (rf ** levels)) if rf != 1.0 else levels
    base_alloc_factor = (1 - rf) / denom
    allocations = []
    for i in range(levels):
        alloc = starting_cash * base_alloc_factor * (rf ** i)
        buy_price = round(initial_price - i * step, 8)
        allocations.append({"level": i+1, "buy_price": buy_price, "alloc_cash": alloc})
    return allocations

def seed_virtual_ledger_if_empty():
    cur.execute("SELECT COUNT(1) FROM virtual_lots")
    if cur.fetchone()[0] > 0:
        return
    # seed initial price
    p = INITIAL_PRICE
    if not p or p <= 0:
        try:
            if api:
                bar = api.get_barset(SYMBOL, 'minute', limit=1)
                if bar and len(bar[SYMBOL])>0:
                    p = float(bar[SYMBOL][0].c)
        except Exception:
            logger.exception("Failed to fetch market price to seed; using configured initial_price if set")
    if not p or p <= 0:
        raise RuntimeError("No initial price available to seed ledger. Set initial_price in config or ensure Alpaca keys are configured.")
    logger.info(f"Seeding virtual ledger at initial price {p}")
    allocs = compute_allocation_levels(p, INITIAL_CASH, RF, LEVELS)
    for a in allocs:
        shares = max(MIN_ORDER_SHARES, int(a["alloc_cash"] // a["buy_price"]))
        sell_target = round(a["buy_price"] + (p * 0.01), 8)  # profit = 1% of initial price
        cur.execute("""INSERT OR IGNORE INTO virtual_lots
            (level, virtual_shares, virtual_cost, buy_price, sell_target, status, created_at)
            VALUES (?,?,?,?,?,?,?)""",
            (a["level"], shares, a["buy_price"]*shares, a["buy_price"], sell_target, "OPEN", int(time.time())))
    conn.commit()

def load_open_virtual_lots() -> List[VirtualLot]:
    cur.execute("SELECT level, virtual_shares, virtual_cost, buy_price, sell_target, status FROM virtual_lots ORDER BY level")
    return [VirtualLot(*r) for r in cur.fetchall()]

# ---------- Alpaca helpers ----------
def get_latest_price() -> Optional[float]:
    try:
        if api:
            trade = api.get_latest_trade(SYMBOL)
            return float(trade.price)
    except Exception:
        logger.exception("Failed to fetch latest trade")
    # fallback: minute bar
    try:
        if api:
            bars = api.get_barset(SYMBOL, 'minute', limit=1)
            if bars and len(bars[SYMBOL])>0:
                return float(bars[SYMBOL][0].c)
    except Exception:
        logger.exception("Fallback price fetch failed")
    return None

def get_actual_position_shares() -> int:
    try:
        if api:
            p = api.get_position(SYMBOL)
            return int(float(p.qty))
    except Exception:
        return 0

def place_market_order(side: str, qty: int) -> Optional[str]:
    if qty <= 0 or not api:
        return None
    try:
        order = api.submit_order(symbol=SYMBOL, qty=qty, side=side, type='market', time_in_force='day')
        cur.execute("INSERT INTO orders (alpaca_id, side, qty, price, status, created_at) VALUES (?,?,?,?,?,?)",
                    (order.id, side, qty, 0.0, order.status, int(time.time())))
        conn.commit()
        logger.info(f"Placed market {side} order qty={qty}")
        return order.id
    except Exception as e:
        logger.exception("Market order failed")
        return None

def place_limit_order(side: str, qty: int, price: float) -> Optional[str]:
    if qty <= 0 or not api:
        return None
    try:
        order = api.submit_order(symbol=SYMBOL, qty=qty, side=side, type='limit', time_in_force='day', limit_price=price)
        cur.execute("INSERT INTO orders (alpaca_id, side, qty, price, status, created_at) VALUES (?,?,?,?,?,?)",
                    (order.id, side, qty, price, order.status, int(time.time())))
        conn.commit()
        logger.info(f"Placed limit {side} order qty={qty} @ {price}")
        return order.id
    except Exception:
        logger.exception("Limit order failed")
        return None

def reconcile_orders():
    try:
        cur.execute("SELECT id, alpaca_id FROM orders WHERE status NOT IN ('filled','canceled')")
        rows = cur.fetchall()
        for rid, aid in rows:
            try:
                o = api.get_order(aid)
                cur.execute("UPDATE orders SET status=? WHERE id=?", (o.status, rid))
            except Exception:
                pass
        conn.commit()
    except Exception:
        logger.exception("Reconcile failed")

# ---------- Safety / Maintenance ----------
def is_paused() -> bool:
    v = read_meta("paused")
    return v == "1"

def set_paused(val: bool):
    write_meta("paused", "1" if val else "0")

# ---------- Core trading loop ----------
async def trading_loop():
    seed_virtual_ledger_if_empty()
    logger.info("Starting trading loop")
    while True:
        try:
            if is_paused():
                logger.info("Bot is paused (maintenance). Sleeping.")
                await asyncio.sleep(POLL_MS/1000)
                continue

            price = get_latest_price()
            if price is None:
                await asyncio.sleep(POLL_MS/1000)
                continue

            # SELL logic: any OPEN virtual lot with sell_target <= price -> sell that lot's virtual_shares
            open_lots = load_open_virtual_lots()
            for lot in open_lots:
                if lot.status == "OPEN" and price >= lot.sell_target:
                    actual_shares = get_actual_position_shares()
                    if actual_shares <= 0:
                        logger.info("No actual shares available to sell (FIFO safety). Skipping sell for level %s", lot.level)
                        continue
                    qty = int(lot.virtual_shares)
                    qty = max(1, qty)
                    logger.info("SELL TRIGGER level=%s sell_target=%s price=%s qty=%s", lot.level, lot.sell_target, price, qty)
                    place_market_order("sell", qty)
                    cur.execute("UPDATE virtual_lots SET status='CLOSED' WHERE level=?", (lot.level,))
                    conn.commit()

            # BUY logic: if price <= buy_price (buy triggers)
            # Ensure we don't exceed MAX_POSITION_SHARES
            actual_shares = get_actual_position_shares()
            cur.execute("SELECT level, virtual_shares, buy_price FROM virtual_lots WHERE status='OPEN' ORDER BY level")
            rows = cur.fetchall()
            for level, vshares, buy_price in rows:
                if price <= buy_price:
                    if actual_shares + vshares > MAX_POSITION_SHARES:
                        logger.info("Safety cap would be exceeded; skipping buy for level %s", level)
                        continue
                    qty = int(vshares)
                    logger.info("BUY TRIGGER level=%s buy_price=%s price=%s qty=%s", level, buy_price, price, qty)
                    place_market_order("buy", qty)
                    actual_shares += qty
                    # Keep virtual lot OPEN until sold
            # reconcile orders
            reconcile_orders()
        except Exception:
            logger.exception("Exception in trading loop")
        await asyncio.sleep(POLL_MS/1000)

# ---------- Web UI (aiohttp) ----------
async def handle_index(request):
    price = get_latest_price()
    pos = get_actual_position_shares()
    # compute cost basis approximate from virtual ledger: sum virtual_cost of CLOSED lots as realized? show open virtual cost
    cur.execute("SELECT SUM(virtual_cost) FROM virtual_lots WHERE status='OPEN'")
    open_cost = cur.fetchone()[0] or 0.0
    cur.execute("SELECT SUM(virtual_cost) FROM virtual_lots WHERE status='CLOSED'")
    closed_cost = cur.fetchone()[0] or 0.0
    html = f"""
    <html>
    <head><title>TQQQ Bot Status</title></head>
    <body>
      <h2>TQQQ Bot Status</h2>
      <p>Symbol: {SYMBOL}</p>
      <p>Current Price: {price}</p>
      <p>Actual Position Shares: {pos}</p>
      <p>Open Virtual Cost (sum): {open_cost:.2f}</p>
      <p>Closed Virtual Cost (sum): {closed_cost:.2f}</p>
      <p>Reduction Factor: {RF}</p>
      <p>Levels configured: {LEVELS}</p>
      <p><a href="/api/levels">View full levels (JSON)</a></p>
      <form method="post" action="/api/clear-logs"><button type="submit">Clear logs</button></form>
      <form method="post" action="/api/pause"><button type="submit">Pause bot</button></form>
      <form method="post" action="/api/resume"><button type="submit">Resume bot</button></form>
      <h3>Recent logs</h3>
      <pre>{tail_log(200)}</pre>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')

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
    app.router.add_get('/api/logs', api_logs)
    app.router.add_post('/api/clear-logs', api_clear_logs)
    app.router.add_post('/api/pause', api_pause)
    app.router.add_post('/api/resume', api_resume)
    return app

# ---------- Main ----------
async def main():
    # start trading loop and web server in parallel
    logger.info("Starting TQQQ bot v2")
    # ensure ledger seeded
    seed_virtual_ledger_if_empty()

    loop = asyncio.get_event_loop()
    app = create_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', WEBUI_PORT)
    await site.start()
    logger.info(f"Web UI listening on port {WEBUI_PORT}")

    # run trading loop forever
    await trading_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down bot")
