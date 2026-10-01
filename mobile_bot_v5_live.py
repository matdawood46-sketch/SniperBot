import os
import threading
import logging
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

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

bot_state = {
    "status": "Connecting to cTrader...",
    "balance": "0",
    "last_trade": "No live trades executed yet."
}

# Initialize cTrader Client
client = Client(HOST, PORT, CLIENT_ID, CLIENT_SECRET)
XAUUSD_SYMBOL_ID = None

def on_connected(client):
    print("✅ Cloud Bot Connected to cTrader! Authenticating App...")
    bot_state["status"] = "Connected. Authenticating..."
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
        print("✅ Account Authorized! Fetching Live Balance & Symbols...")
        bot_state["status"] = "Account Authorized. Fetching Symbol ID..."
        # Fetch Balance
        req_bal = ProtoOATraderReq()
        req_bal.accountId = ACCOUNT_ID
        client.send(req_bal)
        # Fetch Symbol List to find XAUUSD
        req_sym = ProtoOASymbolsListReq()
        req_sym.accountId = ACCOUNT_ID
        client.send(req_sym)
        
    elif msg_name == "ProtoOATraderRes":
        balance = message.balance
        actual_balance = balance / 100.0
        bot_state["balance"] = f"${actual_balance:.2f}"
        
    elif msg_name == "ProtoOASymbolsListRes":
        # Find the Symbol ID for Gold (XAUUSD)
        for symbol in message.symbols:
            if "XAUUSD" in symbol.name or "XAU/USD" in symbol.name:
                XAUUSD_SYMBOL_ID = symbol.symbolId
                print(f"✅ Found XAUUSD Symbol ID: {XAUUSD_SYMBOL_ID}")
                bot_state["status"] = f"Live & Ready. XAUUSD ID: {XAUUSD_SYMBOL_ID}"
                
    elif msg_name == "ProtoOANewOrderRes":
        print("🔥 LIVE TRADE EXECUTED SUCCESSFULLY! 🔥")
        bot_state["last_trade"] = f"✅ {datetime.now(pytz.timezone('Asia/Kuala_Lumpur')).strftime('%H:%M:%S')} - Executed LIVE BUY trade on XAUUSD!"

def on_disconnected(client, reason):
    print(f"❌ Disconnected: {reason}")
    bot_state["status"] = f"Disconnected: {reason}"

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
        h1 { color: #f0b90b; }
        .price { font-size: 2.5em; font-weight: bold; color: #00d39e; margin-top: 10px; }
        .btn { background-color: #ff4d4d; color: black; border: none; padding: 20px; font-size: 1.2em; border-radius: 10px; cursor: pointer; width: 100%; font-weight: bold; box-shadow: 0 4px 8px rgba(0,0,0,0.3);}
        .status-box { background-color: #2d1b2d; border: 1px solid #f0b90b; padding: 15px; border-radius: 8px; margin-top: 20px; }
    </style>
    <script> setTimeout(function(){ window.location.reload(1); }, 5000); </script>
</head>
<body>
    <h1>🤖 Live cTrader Bot</h1>
    <div class="card">
        <h2>Live Demo Balance</h2>
        <div class="price">{{ balance }}</div>
    </div>

    <div class="card">
        <h3>Bot Status</h3>
        <p>{{ status }}</p>
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
    # Run Twisted reactor in background so it doesn't block Flask
    reactor.run(installSignalHandlers=0)

if __name__ == "__main__":
    # Start the cTrader TCP connection in a background thread
    threading.Thread(target=start_reactor, daemon=True).start()
    client.startService()
    
    # Start the Flask Web Server in the main thread
    port = int(os.environ.get("PORT", 5000))
    print(f"📱 Live Dashboard starting on port {port}...")
    app.run(host="0.0.0.0", port=port)