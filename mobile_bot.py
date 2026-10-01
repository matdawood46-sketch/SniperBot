import yfinance as yf
import pandas as pd
import ta
import time
from datetime import datetime
import pytz
from flask import Flask, jsonify, render_template_string, redirect, request
import threading
import requests

# --- CONFIGURATION ---
WATCHLIST = {
    "GOLD": "GC=F",
    "EURUSD": "EURUSD=X"
}
ACCOUNT_BALANCE = 1000.0
RISK_PERCENT = 0.02
MYT = pytz.timezone('Asia/Kuala_Lumpur')
SCAN_INTERVAL = 15

app = Flask(__name__)

# Global state
bot_state = {
    "timestamp": "Starting...",
    "gold_price": "0",
    "eurusd_price": "0",
    "gold_status": "Initializing...",
    "eurusd_status": "Initializing...",
    "last_signal": "None yet. Waiting for sniper bullet...",
    "bot_running": True,
    "news_active": False,
    "news_title": "Checking news..."
}

trade_history = []
last_logged_signal = ""

def is_within_trading_hours():
    now = datetime.now(MYT)
    current_time_float = now.hour + (now.minute / 60.0)
    return (current_time_float >= 10.0 and current_time_float < 19.0) or (current_time_float >= 22.0 or current_time_float < 4.0)

def check_high_impact_news():
    """Fetches live economic news from ForexFactory free API"""
    try:
        # Get today's date in the format required by the API
        today_str = datetime.now().strftime("%Y-%m-%d")
        url = f"https://nfs.faireconomymedia.com/hf/today.json"
        response = requests.get(url, timeout=5)
        news_data = response.json()
        
        now = datetime.now()
        for event in news_data:
            if event.get('country') == 'USD' and event.get('impact') == 'High':
                # Parse the event time
                event_time = datetime.strptime(event['date'], "%Y-%m-%dT%H:%M:%S%z")
                # Check if news is within 15 mins before or after
                time_diff = abs((now - event_time).total_seconds() / 60)
                if time_diff <= 15:
                    return True, event['title']
        return False, "No High Impact US News"
    except Exception as e:
        return False, "News check failed"

def get_market_data(symbol):
    df = yf.download(symbol, period="5d", interval="1m", progress=False)
    if df.empty: return None
    
    clean_df = pd.DataFrame()
    clean_df['Close'] = df['Close'].values.flatten()
    clean_df['High'] = df['High'].values.flatten()
    clean_df['Low'] = df['Low'].values.flatten()
    
    clean_df['EMA_9'] = ta.trend.ema_indicator(clean_df['Close'], window=9)
    clean_df['EMA_50'] = ta.trend.ema_indicator(clean_df['Close'], window=50)
    clean_df['SMA_200'] = ta.trend.sma_indicator(clean_df['Close'], window=200)
    clean_df['RSI'] = ta.momentum.rsi(clean_df['Close'], window=14)
    clean_df.dropna(inplace=True)
    return clean_df

def check_sniper_setup(df):
    current = df.iloc[-1]
    is_uptrend = current['EMA_50'] > current['SMA_200']
    is_downtrend = current['EMA_50'] < current['SMA_200']
    rsi_oversold = current['RSI'] < 40
    rsi_overbought = current['RSI'] > 60
    price_above_9ema = current['Close'] > current['EMA_9']
    price_below_9ema = current['Close'] < current['EMA_9']
    
    if is_uptrend and rsi_oversold and price_above_9ema:
        return "🔥 SNIPER BUY", current['Close']
    elif is_downtrend and rsi_overbought and price_below_9ema:
        return "🔥 SNIPER SELL", current['Close']
    else:
        return "No Setup - Holding fire...", current['Close']

def bot_brain():
    global last_logged_signal
    while True:
        if bot_state["bot_running"]:
            bot_state["timestamp"] = datetime.now(MYT).strftime('%H:%M:%S')
            
            # 1. Check News API
            news_active, news_title = check_high_impact_news()
            bot_state["news_active"] = news_active
            bot_state["news_title"] = news_title
            
            if news_active:
                bot_state["gold_status"] = "🔴 PAUSED FOR NEWS"
                bot_state["eurusd_status"] = "🔴 PAUSED FOR NEWS"
                bot_state["last_signal"] = f"Paused: {news_title}"
            elif not is_within_trading_hours():
                bot_state["gold_status"] = "Outside MYT Trading Hours"
                bot_state["eurusd_status"] = "Outside MYT Trading Hours"
            else:
                # 2. Scan Market
                for asset_name, symbol in WATCHLIST.items():
                    try:
                        df = get_market_data(symbol)
                        if df is not None:
                            status, price = check_sniper_setup(df)
                            price_str = f"${float(price):.2f}"
                            
                            if "GOLD" in asset_name:
                                bot_state["gold_price"] = price_str
                                bot_state["gold_status"] = status
                            else:
                                bot_state["eurusd_price"] = price_str
                                bot_state["eurusd_status"] = status
                                
                            if "SNIPER" in status:
                                bot_state["last_signal"] = f"{datetime.now(MYT).strftime('%H:%M:%S')} - {asset_name} {status} at {price_str}"
                                # 3. Log Trade History
                                new_signal_str = f"{asset_name}{status}{price_str}"
                                if new_signal_str != last_logged_signal:
                                    trade_history.insert(0, {
                                        "time": datetime.now(MYT).strftime('%H:%M:%S'),
                                        "asset": asset_name,
                                        "signal": status,
                                        "price": price_str
                                    })
                                    last_logged_signal = new_signal_str
                    except Exception as e:
                        print(f"Error scanning {asset_name}: {e}")
                    time.sleep(2)
        else:
            bot_state["gold_status"] = "⏸️ BOT PAUSED BY USER"
            bot_state["eurusd_status"] = "⏸️ BOT PAUSED BY USER"
            
        time.sleep(SCAN_INTERVAL)

# --- LEVEL 4 MOBILE DASHBOARD UI ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Sniper Bot Level 4</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: Arial, sans-serif; background-color: {{ bg_color }}; color: #ffffff; text-align: center; padding: 20px; transition: background-color 0.5s; }
        .card { background-color: #1c2530; border-radius: 10px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 8px rgba(0,0,0,0.2); }
        h1 { color: #f0b90b; margin-bottom: 5px; }
        h2 { color: #ffffff; margin-bottom: 5px; }
        .price { font-size: 2.5em; font-weight: bold; color: #00d39e; margin-top: 10px; }
        .status { font-size: 1.2em; color: #a0a0a0; margin-top: 5px; }
        .signal-box { background-color: #2d1b2d; border: 1px solid #f0b90b; padding: 15px; border-radius: 8px; margin-top: 20px; }
        .btn { background-color: #f0b90b; color: black; border: none; padding: 15px 30px; font-size: 1.2em; border-radius: 10px; cursor: pointer; width: 100%; margin-bottom: 20px; font-weight: bold;}
        .news-banner { color: #ff4d4d; font-weight: bold; margin-bottom: 15px; font-size: 1.1em; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px;}
        th, td { border: 1px solid #2c3e50; padding: 10px; text-align: center; font-size: 0.9em;}
        th { background-color: #2c3e50; color: #f0b90b;}
        tr { background-color: #1c2530; }
    </style>
    <script> setTimeout(function(){ window.location.reload(1); }, 5000); </script>
</head>
<body>
    <h1>🤖 Sniper Bot Dashboard</h1>
    <p>Last Scan: {{ timestamp }}</p>
    
    {% if news_active %}
        <div class="news-banner">🔴 HIGH IMPACT NEWS ACTIVE: {{ news_title }}</div>
    {% endif %}

    <form action="/toggle" method="post">
        <button type="submit" class="btn">{% if bot_running %}⏸️ PAUSE BOT{% else %}▶️ RESUME BOT{% endif %}</button>
    </form>
    
    <div class="card">
        <h2>GOLD (XAUUSD)</h2>
        <div class="price">{{ gold_price }}</div>
        <div class="status">{{ gold_status }}</div>
    </div>

    <div class="card">
        <h2>EURUSD</h2>
        <div class="price">{{ eurusd_price }}</div>
        <div class="status">{{ eurusd_status }}</div>
    </div>

    <div class="signal-box">
        <h3>Last Bullet Fired</h3>
        <p>{{ last_signal }}</p>
    </div>

    <div class="card">
        <h3>📜 Trade History Log</h3>
        {% if trade_history %}
        <table>
            <tr><th>Time</th><th>Asset</th><th>Signal</th><th>Price</th></tr>
            {% for trade in trade_history %}
            <tr>
                <td>{{ trade.time }}</td>
                <td>{{ trade.asset }}</td>
                <td>{{ trade.signal }}</td>
                <td>{{ trade.price }}</td>
            </tr>
            {% endfor %}
        </table>
        {% else %}
        <p>No bullets fired yet.</p>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route('/')
def dashboard():
    bg_color = "#3b0d0d" if bot_state["news_active"] else "#0b0f17"
    return render_template_string(HTML_TEMPLATE, trade_history=trade_history, bg_color=bg_color, **bot_state)

@app.route('/toggle', methods=['POST'])
def toggle_bot():
    bot_state["bot_running"] = not bot_state["bot_running"]
    return redirect('/')

if __name__ == "__main__":
    threading.Thread(target=bot_brain, daemon=True).start()
    print("📱 Level 4 Mobile Dashboard Live! Open your phone browser.")
    app.run(host="0.0.0.0", port=5000)