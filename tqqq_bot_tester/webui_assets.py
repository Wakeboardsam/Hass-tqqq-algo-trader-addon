# tqqq_bot_tester/webui_assets.py

def get_dashboard_html(symbol, price, pos, open_cost, closed_cost, reco_status, db_rows, tail_log, is_paused, season_stats):
    
    # Table Rows Logic
    table_rows_html = ""
    for r in db_rows:
        lvl, shs, buy, sell, stat, oid = r
        row_style = ""
        if stat == "OPEN": row_style = "background-color: #e6ffe6; color: #006400;" 
        elif stat == "ORDER_SENT": row_style = "background-color: #fff9e6; color: #b38600;" 
        elif stat == "CLOSED": row_style = "background-color: #ffe6e6; color: #8b0000;" 
        elif stat == "PENDING": row_style = "color: #666;" 

        row_html = f"""
        <tr style="{row_style}">
            <td>{lvl}</td><td><strong>{stat}</strong></td><td>{shs}</td>
            <td>${buy:.2f}</td><td>${sell:.2f}</td>
            <td style="font-size: 0.8em; font-family: monospace;">{oid if oid else '-'}</td>
        </tr>"""
        table_rows_html += row_html

    # Alerts
    alerts_html = ""
    if is_paused:
        alerts_html += "<div style='background:#fff3cd; color:#856404; padding:10px; margin:10px 0;'><strong>PAUSED</strong></div>"

    pl_color = "green" if season_stats['current_pl'] >= 0 else "red"

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>SIMULATION: {symbol}</title>
        <meta http-equiv="refresh" content="2"> <style>
            body {{ font-family: sans-serif; padding: 20px; background-color: #f0f0f0; }}
            .sim-banner {{ background: #6f42c1; color: white; padding: 10px; text-align: center; font-weight: bold; border-radius: 5px; margin-bottom: 20px; }}
            .card-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 20px; }}
            .card {{ background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            .card h4 {{ margin: 0 0 5px 0; color: #666; font-size: 0.8em; text-transform: uppercase; }}
            .card p {{ margin: 0; font-size: 1.1em; font-weight: bold; }}
            table {{ border-collapse: collapse; width: 100%; background: white; }}
            th, td {{ padding: 10px; text-align: center; border-bottom: 1px solid #eee; }}
            th {{ background: #ddd; }}
            pre {{ background: #222; color: #0f0; padding: 15px; max-height: 300px; overflow-y: auto; }}
        </style>
    </head>
    <body>
        <div class="sim-banner">🧪 SIMULATION MODE - NO REAL MONEY 🧪</div>
        
        <div style="display: flex; justify-content: space-between;">
            <h1>{symbol} Tester</h1>
            <p>Time: {reco_status.get('timestamp')}</p>
        </div>

        {alerts_html}

        <div class="card-grid">
            <div class="card"><h4>Simulated Price</h4><p style="color:blue; font-size:1.4em;">${price}</p></div>
            <div class="card"><h4>Simulated Shares</h4><p>{pos}</p></div>
            <div class="card"><h4>Current Season P/L</h4><p style="color:{pl_color}">${season_stats['current_pl']:,.2f}</p></div>
            <div class="card"><h4>Simulated Cash</h4><p>${reco_status['alpaca_cash']:,.2f}</p></div>
        </div>

        <form method="post" action="/api/clear-db" style="margin-bottom: 20px;">
            <button style="background:red; color:white; padding:10px; border:none; cursor:pointer;">RESET SIMULATION</button>
        </form>

        <h3>Strategy Ledger</h3>
        <table>
            <thead><tr><th>Level</th><th>Status</th><th>Shares</th><th>Buy Target</th><th>Sell Target</th><th>Sim Order ID</th></tr></thead>
            <tbody>{table_rows_html}</tbody>
        </table>

        <h3>Simulation Logs</h3>
        <pre>{tail_log}</pre>
    </body>
    </html>
    """
