# Order Flow Chart

A real-time order flow chart for NIFTY futures, built with Flask (Python) for the backend and D3.js for the frontend. The chart visualizes buy and sell volumes at different price levels over time, with a Last Traded Price (LTP) indicator.

## Features
- Real-time updates using Server-Sent Events (SSE) and Angel One's SmartAPI WebSocket.
- Visualizes buy and sell volumes as blocks
- LTP line and text
- User-defined time interval and tick size for aggregating trades and rendering price levels.
- Dynamic panning in both X and Y directions to adjust the visible range of time buckets and price levels.
- Canvas dynamically filled with time buckets and price levels based on the canvas size, time interval, and tick size.

## Project Structure
order-flow-chart/
│
├── app.py             
├── templates/
│   └── index.html     
├── requirements.txt    
└── README.md          


## Requirements
- Python 3.6+
- Angel One API credentials (AUTH_TOKEN, API_KEY, CLIENT_CODE, PASS)
- Git (for version control)

## Setup Instructions
1. **Clone the Repository** (after pushing to GitHub, see below for instructions):
   git clone https://github.com/your-username/order-flow-chart.git
   cd order-flow-chart

## Install Dependencies:
Create a virtual environment and install the required Python packages:
bash

python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

## Update API Credentials:
Open app.py and replace the placeholder Angel One API credentials with your actual credentials:
python

AUTH_TOKEN = "your-auth-token"
API_KEY = "your-api-key"
CLIENT_CODE = "your-client-code"
PASS = "your-password"

## Run the Application:
Start the Flask server:
bash

python app.py

Open your browser and navigate to http://localhost:5000.

## Usage
The chart displays buy and sell volumes at different price levels over time.

Use the input fields to set the time interval (in minutes) and tick size for aggregating trades and rendering price levels.

Click and drag the chart to pan in both X (time) and Y (price) directions to adjust the visible range.

The LTP line and text update in real-time, with the line ending at the current time bucket and the text in the next bucket.

## Dependencies
Flask: Web framework for the backend.

SmartAPI-Python: Angel One API client for WebSocket data.

PyOTP: For generating TOTP for authentication.

Logzero: For logging.

D3.js: For rendering the chart in the frontend (loaded via CDN).

## Contributing
Fork the repository.

Create a new branch (git checkout -b feature/your-feature).

Make your changes and commit them (git commit -m "Add your feature").

Push to your fork (git push origin feature/your-feature).

Open a pull request.

