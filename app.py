from flask import Flask, render_template, jsonify, request, Response
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
from SmartApi.smartConnect import SmartConnect
from logzero import logger
from datetime import datetime, timedelta
import pyotp
import time
import threading
from queue import Queue
import json
import threading

app = Flask(__name__)

# Angel One API credentials (replace with actual values)

AUTH_TOKEN = "xxxxxxxxxxxxxxxxxxx"
API_KEY = "xxxxxx"
CLIENT_CODE = "xxxxx"
PASS = "xxxx"

# Initialize SmartConnect and WebSocket
smartApi = SmartConnect(API_KEY)
try:
    totp = pyotp.TOTP(AUTH_TOKEN).now()
except Exception as e:
    logger.error("Invalid Token: The provided token is not valid.")
    raise e

data = smartApi.generateSession(CLIENT_CODE, PASS, totp)
if not data['status']:
    logger.error(data)
else:
    authToken = data['data']['jwtToken']
    FEED_TOKEN = smartApi.getfeedToken()

correlation_id = "niftyfut"
mode = 2
token_list = [{"exchangeType": 2, "tokens": ["35001"]}]  # NIFTY futures token

sws = SmartWebSocketV2(authToken, API_KEY, CLIENT_CODE, FEED_TOKEN)

Lotsize = 75

# Store previous tick data
previous_tick = {
    "timestamp": None,
    "ltp": None,
    "ltq": None,
    "total_traded_volume": None,
    "trade_direction": None
}

# Aggregate trades by time bucket and price level
trade_data = {}
current_time_bucket = None
time_interval_minutes = 3  # Default to 3 minutes
tick_size = 3  # Default tick size, will be updated by user input
last_traded_price = None  # Track LTP
processing_lock = threading.Lock()  # Lock for synchronizing data processing
is_processing = True  # Flag to control WebSocket processing

# Queue to push updates to the frontend
update_queue = Queue()

def get_time_bucket(timestamp, interval_minutes):
    """Round timestamp to the nearest time bucket (e.g., 3-minute intervals)."""
    minutes = timestamp.minute
    bucket_minute = (minutes // interval_minutes) * interval_minutes
    return timestamp.replace(minute=bucket_minute, second=0, microsecond=0)

def process_tick(data):
    global previous_tick, trade_data, current_time_bucket, time_interval_minutes, last_traded_price

    with processing_lock:
        if not is_processing:
            return  # Skip processing if we're updating the interval

        # Extract last traded timestamp
        timestamp = datetime.fromtimestamp(data.get("last_traded_timestamp", time.time()))
        
        # Update LTP
        last_traded_price = data.get("last_traded_price", 0) / 100
        
        # Determine the current time bucket
        new_time_bucket = get_time_bucket(timestamp, time_interval_minutes)
        
        # If the time bucket has changed, reset the data for the new bucket
        if current_time_bucket != new_time_bucket:
            current_time_bucket = new_time_bucket
            if current_time_bucket not in trade_data:
                trade_data[current_time_bucket] = {}
        
        # Extract key fields and divide price values by 100
        ltp = data.get("last_traded_price", 0) / 100
        ltq = data.get("last_traded_quantity", 0)
        total_traded_volume = data.get("volume_trade_for_the_day", 0)
        
        if total_traded_volume == previous_tick["total_traded_volume"]:
            return
        else:
            trade_direction = None
            trade_size = (total_traded_volume - previous_tick["total_traded_volume"]) // Lotsize if previous_tick["total_traded_volume"] is not None else 0
            # Determine trade direction
            if previous_tick["total_traded_volume"] is not None:
                if total_traded_volume > previous_tick["total_traded_volume"]:
                    
                    if ltp > previous_tick["ltp"]:
                        trade_direction = "BUY"
                    elif ltp < previous_tick["ltp"]:
                        trade_direction = "SELL"
                    else:
                        trade_direction = previous_tick["trade_direction"]

                    # Round price to nearest tick size (user-defined)
                    price_level = round(ltp / tick_size) * tick_size

                    # Aggregate buy/sell volumes in the current time bucket
                    if price_level not in trade_data[current_time_bucket]:
                        trade_data[current_time_bucket][price_level] = {"buy_volume": 0, "sell_volume": 0}
                    
                    if trade_direction == "BUY":
                        trade_data[current_time_bucket][price_level]["buy_volume"] += trade_size
                    elif trade_direction == "SELL":
                        trade_data[current_time_bucket][price_level]["sell_volume"] += trade_size

                    print(f"New Trade: Time={timestamp}, Price={price_level:.2f}, Size={trade_size}, Type={trade_direction}")

                    # Push update to the queue
                    update_queue.put({
                        "trade_data": {str(k): v for k, v in trade_data.items()},
                        "ltp": last_traded_price
                    })

            # Update previous tick data
            previous_tick = {
                "timestamp": timestamp,
                "ltp": ltp,
                "ltq": ltq,
                "total_traded_volume": total_traded_volume,
                "trade_direction": trade_direction
            }

def on_data(wsapp, message):
    try:
        data = message
        if "subscription_mode" in data and data["subscription_mode"] == 2:
            process_tick(data)
    except Exception as e:
        print(f"Error processing message: {e}")

def on_open(wsapp):
    sws.subscribe(correlation_id, mode, token_list)

def on_error(wsapp, error):
    logger.error(error)

def on_close(wsapp):
    logger.info("Connection closed")

sws.on_open = on_open
sws.on_data = on_data
sws.on_error = on_error
sws.on_close = on_close

# Start WebSocket in a separate thread
def start_websocket():
    sws.connect()

threading.Thread(target=start_websocket, daemon=True).start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data')
def get_data():
    return jsonify({str(k): v for k, v in trade_data.items()})

@app.route('/set_interval', methods=['POST'])
def set_interval():
    global time_interval_minutes, tick_size, is_processing, trade_data, current_time_bucket
    with processing_lock:
        is_processing = False  # Pause processing
        interval = int(request.form['interval'])
        tick_size = float(request.form['tickSize'])  # Get tick size from frontend
        time_interval_minutes = interval
        # Reset trade data to start fresh with new interval and tick size
        trade_data.clear()
        current_time_bucket = None
        is_processing = True  # Resume processing
    return jsonify({"status": "success", "interval": time_interval_minutes, "tickSize": tick_size})

@app.route('/stream')
def stream():
    def generate():
        while True:
            if not update_queue.empty():
                update = update_queue.get()
                yield f"data: {json.dumps(update)}\n\n"
            time.sleep(0.1)  # Small sleep to prevent busy-waiting
    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
