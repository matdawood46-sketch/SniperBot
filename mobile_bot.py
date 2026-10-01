import os
import threading
import logging
import time
from twisted.internet import reactor
from flask import Flask, render_template_string, redirect, request
from ctrader_open_api import Client
from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import *
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import *
import pytz
from datetime import datetime

# --- CONFIGURATION ---
CLIENT_ID = "42016_LBIrGUlJbeq1EAYPzJxjG3bSLisJQ9Z94G7XQNmveczUvNRf4V"
CLIENT_SECRET = "RuiuJiVHNp5ieuKmCEy4FUKrBLQGsatRCvBB9IgA0m7Q6P2Tmi"
ACCESS_TOKEN = "ahZGJf-XRgJhvxNXw-IzZKWJnu0ThmJXEsOJEtXeSug"
ACCOUNT_ID = 48979635

HOST = "openapi.ctrader.com"
PORT = 5034  # Demo Port
MYT = pytz.timezone('Asia/Kuala_Lumpur')

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

bot_state = {
    "connection_status": "🔴 CONNECTING...",
    "balance": "$0",
    "equity": "$0",
    "floating_pl": "$0.00",
    "pl_color": "#ffffff",
    "open_trades": "0",
    "last_trade": "No live trades executed yet."
}

client = Client(HOST, PORT, CLIENT_ID, CLIENT_SECRET)
XAUUSD_SYMBOL_ID = None

def on_connected(client):
    print("✅ Cloud Bot Connected! Authenticating App...")
    req = ProtoOAuthClientAppAuthentication()
    req.clientId = CLIENT_ID
    req.clientSecret = CLIENT_SECRET
    client.send(req)

def on_message_received(client, message):
    global XAUUSD_SYMBOL_ID
    msg_name = message.__class__.__name__
    print(f"📡 Received: {msg_name}")
    
    if msg_name == "ProtoOaClientAppAuthRes":
        print("✅ App Authenticated! Authorizing Trading Account...")
        req = ProtoOAAccountAuthReq()
        req.clientId = CLIENT_ID
        req.accessToken = ACCESS_TOKEN
        req.accountId = ACCOUNT_ID
        client.send(req)
        
    elif msg_name == "ProtoOAAccountAuthRes":
        print("✅ Account Authorized! Cloud Bot is LIVE.")
        bot_state["connection_status"] = "🟢 LIVE CONNECTED"
        # Start the background data polling thread
        threading.Thread(target=data_refresh_loop, daemon=True).start()
        # Fetch symbols
        req_sym = ProtoOASymbolsListReq()
        req_sym.accountId = ACCOUNT_ID
        client.send(req_sym)
        
    elif msg_name == "ProtoOASymbolsListRes":
        for symbol in message.symbols:
            if "XAUUSD" in symbol.name:
                XAUUSD_SYMBOL_ID = symbol.symbolId
                print(f"✅ Found XAUUSD Symbol ID: {XAUUSD_SYMBOL_ID}")
                
    elif msg_name == "ProtoOATraderRes":
        bal = message.balance / 100.0
        eq = message.equity / 100.0
        pl = eq - bal
        
        bot_state["balance"] = f"${bal:.2f}"
        bot_state["equity"] = f"${eq:.2f}"
        bot_state["floating_pl"] = f"${pl:.2f}"
        bot_state["pl_color"] = "#00d39e" if pl >= 0 else "#ff4d4d"
        
    elif msg_name == "ProtoOAPositionListRes":
        bot_state["open_trades"] = str(len(message.position))
        
    elif msg_name == "ProtoOANewOrderRes":
        print("🔥 LIVE TRADE EXECUTED SUCCESSFULLY! 🔥")
        bot_state["last_trade"] = f"✅ {datetime.now(MYT).strftime('%H:%M:%S')} - LIVE BUY order executed successfully!"

def on_disconnected(client, reason):
    print(f"❌ Disconnected: {reason}")
    bot_state["connection_status"] = f"❌ DISCONNECTED: {reason}"

# Background loop to fetch live Balance, Equity, and Positions
def data_refresh_loop():
    while True:
        try:
            # Request Balance & Equity
            req = ProtoOATraderReq()
            req.accountId = ACCOUNT_ID
            client.send(req)
            
            # Request Open Positions
            req_pos = ProtoOAPositionListReq()
            req_pos.accountId = ACCOUNT_ID
            req_pos.ctidTraderAccountId = ACCOUNT_ID
            client.send(req_pos)
        except Exception as e:
            print("Polling error:", e)
        time.sleep(15)

client.setConnectedCallback(on_connected)
client.setMessageReceivedCallback(on_message_received)
client.setDisconnectedCallback(on_disconnected)

# --- MOBILE DASHBOARD UI ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Sniper Bot Level 5 - Live</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: Arial, sans-serif; background-color: #0b0f17; color: #ffffff; text-align: center; padding: 20px; }
        .card { background-color: #1c2530; border-radius: 10px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 8px rgba(0,0,0,0.2); }
        h1 { color: #f0b90b; margin-bottom: 5px; }
        h2 { color: #ffffff; margin-bottom: 5px; }
        .price { font-size: 2.5em; font-weight: bold; color: #00d39e; margin-top: 10px; }
        .pl { font-size: 2em; font-weight: bold; margin-top: 10px; color: {{ pl_color }}; }
        .status-box { background-color: #2d1b2d; border: 1px solid #f0b90b; padding: 15px; border-radius: 8px; margin-top: 20px; }
        .btn { background-color: #ff4d4d; color: black; border: none; padding: 20px; font-size: 1.2em; border-radius: 10px; cursor: pointer; width: 100%; font-weight: bold; }
        .status-light { font-size: 1.2em; font-weight: bold; color: #f0b90b; margin-bottom: 15px; }
    </style>
    <script> setTimeout(function(){ window.location.reload(1); }, 5000); </script>
</head>
<body>
    <h1>🤖 Live cTrader Bot</h1>
    <div class="status-light">{{ connection_status }}</div>
    
    <div class="card">
        <h2>Live Demo Balance</h2>
        <div class="price">{{ balance }}</div>
    </div>

    <div class="card">
        <h2>Live Equity</h2>
        <div class="price">{{ equity }}</div>
    </div>

    <div class="card">
        <h2>Floating P/L (Live Trades)</h2>
        <div class="pl">{{ floating_pl }}</div>
        <p>Open Trades: {{ open_trades }}</p>
    </div>

    <div class="status-box">
        <h3>Last Live Trade</h3>
        <p>{{ last_trade }}</p>
    </div>

    <br>
    <form action="/execute_live_trade" method="post">
        <button type="submit" class="btn">⚡ EXECUTE LIVE DEMO TRADE (BUY XAUUSD)</button>
    </form>
</body>
</html>
"""

@app.route('/')
def dashboard():
    return render_template_string(HTML_TEMPLATE, **bot_state)

@app.route('/execute_live_trade', methods=['POST'])
def execute_live_trade():
    global XAUUSD_SYMBOL_ID
    if XAUUSD_SYMBOL_ID:
        print(f"⚡ Firing Live Order for XAUUSD (ID: {XAUUSD_SYMBOL_ID})...")
        req = ProtoOANewOrderReq()
        req.accountId = ACCOUNT_ID
        req.symbolId = XAUUSD_SYMBOL_ID
        req.orderType = 1 # MARKET ORDER
        req.tradeSide = 1 # BUY
        req.volume = 1000 # 0.01 lots (1000 units)
        client.send(req)
    else:
        print("Cannot execute trade: XAUUSD Symbol ID not found yet.")
    return redirect('/')

# --- TWISTED + FLASK CLOUD RUNNER ---
def start_reactor():
    # Crucial Fix: Start the cTrader service when the reactor is ready
    reactor.callWhenRunning(client.startService)
    reactor.run(installSignalHandlers=0)

if __name__ == "__main__":
    # Start the cTrader TCP connection in a background thread
    threading.Thread(target=start_reactor, daemon=True).start()
    
    # Start the Flask Web Server in the main thread
    port = int(os.environ.get("PORT", 5000))
    print(f"📱 Live Dashboard starting on port {port}...")
    app.run(host="0.0.0.0", port=port)