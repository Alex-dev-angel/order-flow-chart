import os
from dotenv import load_dotenv
from flask import Flask, render_template, jsonify, request, Response
from datetime import datetime, timedelta
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from pytz import timezone as ZoneInfo
import time
import threading
import json
from queue import Queue, Empty
import logging
import sqlite3

# --- Python Standard Libraries for Broker ---
import pyotp
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
from SmartApi.smartConnect import SmartConnect

# --- Basic Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(threadName)s - %(message)s')
app = Flask(__name__)
load_dotenv()

# ==============================================================================
# --- BROKER CREDENTIALS & SETTINGS (ACTION REQUIRED) ---
# ==============================================================================
API_KEY = os.getenv("API_KEY")
CLIENT_CODE = os.getenv("CLIENT_CODE")
PASS = os.getenv("PASS")
AUTH_TOKEN = os.getenv("AUTH_TOKEN") # The secret key from your 2FA app, not the 6-digit code

INSTRUMENT_TOKEN = os.getenv("INSTRUMENT_TOKEN") 
LOTSIZE = int(os.getenv("LOTSIZE", 75))
# ==============================================================================
# --- DATABASE CONFIGURATION ---
DB_NAME = os.getenv("DB_NAME", "trading_data_SEP.db")
# ==============================================================================

# --- Application State (Shared between threads) ---
time_interval_minutes = 5
tick_size = 2
trade_data = {} # In-memory store for candles, hydrated from DB at startup
processing_lock = threading.Lock()
update_queue = Queue()

previous_tick = {
    "total_traded_volume": None,
    "ltp": None,
    "trade_direction": None,
}

# --- Database Functions ---

def init_db():
    """Initializes the SQLite database and creates the candles table if it doesn't exist."""
    try:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS candles (
                instrument_token TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                footprint_json TEXT,
                PRIMARY KEY (instrument_token, timestamp)
            )
        ''')
        conn.commit()
        conn.close()
        logging.info(f"Database '{DB_NAME}' initialized successfully.")
    except Exception as e:
        logging.error(f"Error initializing database: {e}")

def save_candle_to_db(candle_data):
    """Saves a single completed candle to the SQLite database."""
    try:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        cursor = conn.cursor()
        footprint_json = json.dumps(candle_data['levels'])
        
        # Use INSERT OR REPLACE to handle potential duplicates (acts as an upsert)
        cursor.execute('''
            INSERT OR REPLACE INTO candles (instrument_token, timestamp, open, high, low, close, footprint_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            INSTRUMENT_TOKEN,
            candle_data['time'],
            candle_data['open'],
            candle_data['high'],
            candle_data['low'],
            candle_data['close'],
            footprint_json
        ))
        conn.commit()
        conn.close()
        logging.info(f"Saved candle for timestamp {candle_data['time']} to database.")
    except Exception as e:
        logging.error(f"Error saving candle to DB for timestamp {candle_data['time']}: {e}")

def load_history_from_db():
    """Loads all candles for the instrument from the DB into the in-memory trade_data dict."""
    global trade_data
    try:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        conn.row_factory = sqlite3.Row # Allows accessing columns by name
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM candles WHERE instrument_token = ? ORDER BY timestamp ASC", (INSTRUMENT_TOKEN,))
        rows = cursor.fetchall()
        
        with processing_lock:
            for row in rows:
                ts = datetime.fromtimestamp(row['timestamp'], ZoneInfo("Asia/Kolkata"))
                levels = json.loads(row['footprint_json'])
                
                # Reconstruct the levels map
                levels_map = {level['price']: {'bidVol': level['bidVol'], 'askVol': level['askVol']} for level in levels}
                
                trade_data[ts] = {
                    "open": row['open'], "high": row['high'], "low": row['low'], "close": row['close'],
                    "levels": levels_map
                }
        conn.close()
        logging.info(f"Loaded {len(rows)} historical candles from database for token {INSTRUMENT_TOKEN}.")
    except Exception as e:
        logging.error(f"Error loading history from DB: {e}")

# --- Data Processing Logic ---

def get_time_bucket(timestamp, interval_minutes):
    minutes = (timestamp.minute // interval_minutes) * interval_minutes
    return timestamp.replace(minute=minutes, second=0, microsecond=0)

def process_and_queue_bar_update(tick_for_processing):
    global trade_data, time_interval_minutes, tick_size

    with processing_lock:
        timestamp = tick_for_processing['timestamp']
        ltp = tick_for_processing['ltp']
        price_level = round(ltp / tick_size) * tick_size
        current_bucket_ts = get_time_bucket(timestamp, time_interval_minutes)

        # --- CANDLE CLOSE DETECTION & DB SAVE ---
        # If the bucket has changed, the previous one is now complete.
        if trade_data and current_bucket_ts not in trade_data:
            # Get the timestamp of the bar that just finished
            last_completed_bucket_ts = sorted(trade_data.keys())[-1]
            completed_bar_data = format_bar_for_frontend(last_completed_bucket_ts)
            if completed_bar_data:
                # Save the completed bar to the database
                save_candle_to_db(completed_bar_data)

        if current_bucket_ts not in trade_data:
            trade_data[current_bucket_ts] = {
                "open": price_level, "high": price_level, "low": price_level, "close": price_level,
                "levels": {}
            }
        
        bar = trade_data[current_bucket_ts]
        bar["high"] = max(bar["high"], price_level)
        bar["low"] = min(bar["low"], price_level)
        bar["close"] = price_level

        if price_level not in bar["levels"]:
            bar["levels"][price_level] = {"bidVol": 0, "askVol": 0}

        if tick_for_processing['direction'] == "BUY":
            bar["levels"][price_level]["askVol"] += tick_for_processing['volume']
        else:
            bar["levels"][price_level]["bidVol"] += tick_for_processing['volume']

        live_bar_update = format_bar_for_frontend(current_bucket_ts)
        if live_bar_update:
            update_queue.put(live_bar_update)

def format_bar_for_frontend(timestamp):
    if timestamp not in trade_data: return None
    bar_data = trade_data[timestamp]
    levels = [{"price": float(p), "bidVol": v["bidVol"], "askVol": v["askVol"]} for p, v in bar_data["levels"].items()]
    levels.sort(key=lambda x: x['price'], reverse=True)
    return {
        "time": int(timestamp.astimezone(ZoneInfo("Asia/Kolkata")).timestamp()),
        "open": bar_data["open"], "high": bar_data["high"],
        "low": bar_data["low"], "close": bar_data["close"],
        "levels": levels
    }

# --- Broker Connection and Data Handling ---

def start_broker_connection():
    # (This entire function is identical to the previous version)
    global previous_tick
    logging.info("Attempting to connect to the broker...")
    try:
        smartApi = SmartConnect(API_KEY)
        totp = pyotp.TOTP(AUTH_TOKEN).now()
        session_data = smartApi.generateSession(CLIENT_CODE, PASS, totp)
        if not session_data['status']:
            logging.error(f"Broker authentication failed: {session_data['message']}")
            return
        authToken = session_data['data']['jwtToken']
        FEED_TOKEN = smartApi.getfeedToken()
        logging.info("Broker authentication successful.")
    except Exception as e:
        logging.error(f"An error occurred during authentication: {e}")
        return

    def on_open(wsapp):
        logging.info("Broker WebSocket connection opened.")
        sws.subscribe("footprint_chart", 2, [{"exchangeType": 2, "tokens": [INSTRUMENT_TOKEN]}])
        logging.info(f"Subscribed to instrument token: {INSTRUMENT_TOKEN}")

    def on_data(wsapp, message):
        global previous_tick
        try:
            if "subscription_mode" not in message or message["subscription_mode"] != 2: return
            ltp = message.get("last_traded_price", 0) / 100
            total_traded_volume = message.get("volume_trade_for_the_day", 0)
            if previous_tick["total_traded_volume"] is None:
                previous_tick["total_traded_volume"] = total_traded_volume
                previous_tick["ltp"] = ltp
                return
            if total_traded_volume == previous_tick["total_traded_volume"]: return
            trade_size = (total_traded_volume - previous_tick["total_traded_volume"])
            trade_direction = "BUY" if ltp > previous_tick["ltp"] else ("SELL" if ltp < previous_tick["ltp"] else previous_tick["trade_direction"])
            if trade_direction and trade_size > 0:
                tick_for_processing = {
                    'timestamp': datetime.fromtimestamp(message.get("last_traded_timestamp", time.time()), ZoneInfo("Asia/Kolkata")),
                    'ltp': ltp, 'volume': trade_size / LOTSIZE, 'direction': trade_direction
                }
                process_and_queue_bar_update(tick_for_processing)
            previous_tick["total_traded_volume"] = total_traded_volume
            previous_tick["ltp"] = ltp
            previous_tick["trade_direction"] = trade_direction
        except Exception as e:
            logging.error(f"Error processing broker message: {e}")

    def on_error(wsapp, error): logging.error(f"Broker WebSocket error: {error}")
    def on_close(wsapp, code, msg): logging.info("Broker WebSocket connection closed.")
    sws = SmartWebSocketV2(authToken, API_KEY, CLIENT_CODE, FEED_TOKEN)
    sws.on_open = on_open
    sws.on_data = on_data
    sws.on_error = on_error
    sws.on_close = on_close
    sws.connect()

# --- Flask Web Server Routes ---

@app.route('/')
def index(): return render_template('index.html')

@app.route('/history')
def get_history():
    with processing_lock:
        keys = sorted(trade_data.keys())
        completed_keys = keys[:-1] if len(keys) > 1 else keys
        history = [format_bar_for_frontend(ts) for ts in completed_keys]
        return jsonify(history)

@app.route('/settings', methods=['GET', 'POST'])
def settings_route():
    global time_interval_minutes, tick_size, trade_data
    if request.method == 'POST':
        with processing_lock:
            time_interval_minutes = int(request.json['interval'])
            tick_size = float(request.json['tickSize'])
            trade_data.clear()
            while not update_queue.empty():
                try: update_queue.get_nowait()
                except Empty: continue
        return jsonify({"status": "success"})
    else:
        return jsonify({"interval": time_interval_minutes, "tickSize": tick_size})

@app.route('/stream')
def stream():
    def generate():
        while True:
            try:
                update = update_queue.get(timeout=30)
                yield f"data: {json.dumps(update)}\n\n"
            except Empty:
                yield ": keep-alive\n\n"
    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    # --- APPLICATION STARTUP SEQUENCE ---
    # 1. Initialize the database schema
    init_db()

    # 2. Load historical data from the database into memory
    load_history_from_db()

    # 3. Start the broker connection in a background thread
    broker_thread = threading.Thread(target=start_broker_connection, name="BrokerThread", daemon=True)
    broker_thread.start()
    
    # 4. Start the Flask web server (using Waitress) in the main thread
    from waitress import serve
    logging.info("Starting Flask app with Waitress server on http://0.0.0.0:5002")
    serve(app, host='0.0.0.0', port=5002)