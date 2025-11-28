# tqqq_algo_trader_v2/webui_assets.py

def get_dashboard_html(symbol, price, pos, open_cost, closed_cost, reco_status, db_rows, tail_log, is_paused):
    """
    Generates the complete HTML dashboard for the trading bot.
    Separating this from the main logic makes the bot code cleaner and safer.
    """
    
    # --- 1. Construct the Table Rows ---
    table_rows_html = ""
    for r in db_rows:
        lvl, shs, buy, sell, stat, oid = r
        
        # Color Logic: Green for Open, Yellow for Pending Orders, Red for Closed
        row_style = ""
        if stat == "OPEN":
            row_style = "background-color: #e6ffe6; color: #006400;" # Light Green / Dark Green
        elif stat == "ORDER_SENT":
            row_style = "background-color: #fff9e6; color: #b38600;" # Light Yellow / Dark Gold
        elif stat == "CLOSED":
            row_style = "background-color: #ffe6e6; color: #8b0000;" # Light Red / Dark Red
        elif stat == "PENDING":
            row_style = "color: #666;" # Gray text for future levels

        row_html = f"""
        <tr style="{row_style}">
            <td>{lvl}</td>
            <td><strong>{stat}</strong></td>
            <td>{shs}</td>
            <td>${buy:.2f}</td>
            <td>${sell:.2f}</td>
            <td style="font-size: 0.8em; font-family: monospace;">{oid if oid else '-'}</td>
        </tr>
        """
        table_rows_html += row_html

    # --- 2. Construct Alerts ---
    alerts_html = ""
    
    # Reconciliation Alert (Critical)
    if not reco_status['reconciled']:
        alerts_html += f"""
        <div style="background-color: #ffcccc; border: 1px solid red; color: red; padding: 15px; margin-bottom: 20px; border-radius: 5px;">
            <strong>CRITICAL WARNING:</strong> Share Mismatch!<br>
            Database expects {reco_status['assumed_shares']} shares, but Alpaca has {reco_status['actual_shares']}.<br>
            The bot is <strong>PAUSED</strong> until you fix this.
        </div>
        """
        
    # Paused Alert (Manual)
    if is_paused:
        alerts_html += f"""
        <div style="background-color: #fff3cd; border: 1px solid #ffeeba; color: #856404; padding: 15px; margin-bottom: 20px; border-radius: 5px;">
            <strong>Bot is PAUSED.</strong> No new trades will be executed.
        </div>
        """

    # --- 3. Return Full HTML Page ---
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{symbol} Grid Bot V2</title>
        <meta http-equiv="refresh" content="5"> <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; padding: 20px; background-color: #f9f9f9; }}
            h1 {{ margin-top: 0; }}
            
            /* Status Cards */
            .card-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }}
            .card {{ background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            .card h4 {{ margin: 0 0 10px 0; color: #666; font-size: 0.9em; text-transform: uppercase; }}
            .card p {{ margin: 0; font-size: 1.2em; font-weight: bold; }}
            
            /* Table Styling */
            table {{ border-collapse: collapse; width: 100%; background: white; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden; }}
            th, td {{ padding: 12px 15px; text-align: center; border-bottom: 1px solid #eee; }}
            th {{ background-color: #f8f9fa; font-weight: 600; color: #333; }}
            tr:last-child td {{ border-bottom: none; }}
            
            /* Buttons */
            .btn-group {{ margin-bottom: 20px; }}
            button {{ padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; margin-right: 5px; }}
            button.pause {{ background-color: #ffc107; color: #212529; }}
            button.resume {{ background-color: #28a745; color: white; }}
            button.danger {{ background-color: #dc3545; color: white; opacity: 0.8; }}
            
            /* Logs */
            pre {{ background: #212529; color: #f8f9fa; padding: 15px; border-radius: 8px; max-height: 400px; overflow-y: auto; font-size: 0.85em; }}
        </style>
    </head>
    <body>
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <h1>{symbol} Grid Bot Dashboard</h1>
            <div>
                <span style="font-size: 0.9em; color: #666;">Last Update: {reco_status.get('timestamp', '')}</span>
            </div>
        </div>

        {alerts_html}

        <div class="card-grid">
            <div class="card">
                <h4>Market Price</h4>
                <p>${price}</p>
            </div>
            <div class="card">
                <h4>Shares Held</h4>
                <p>{pos}</p>
            </div>
            <div class="card">
                <h4>Active Cash</h4>
                <p>${open_cost:,.2f}</p>
            </div>
            <div class="card">
                <h4>Buying Power</h4>
                <p>${reco_status['alpaca_cash']:,.2f}</p>
            </div>
        </div>

        <div class="btn-group">
            <form method="post" action="/api/pause" style="display:inline;"><button class="pause">PAUSE</button></form>
            <form method="post" action="/api/resume" style="display:inline;"><button class="resume">RESUME</button></form>
            <form method="post" action="/api/clear-logs" style="display:inline;"><button>Clear Logs</button></form>
            <form method="post" action="/api/clear-db" style="display:inline;"><button class="danger">RESET DATABASE</button></form>
        </div>

        <h3>Strategy Ledger</h3>
        <table>
            <thead>
                <tr>
                    <th>Level</th>
                    <th>Status</th>
                    <th>Shares</th>
                    <th>Buy Target</th>
                    <th>Sell Target</th>
                    <th>Order ID</th>
                </tr>
            </thead>
            <tbody>
                {table_rows_html}
            </tbody>
        </table>

        <h3>System Logs</h3>
        <pre>{tail_log}</pre>
    </body>
    </html>
    """
