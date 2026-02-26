#!/usr/bin/env python3
"""
KALSHI DATA LOGGER - Cloud Version (Google Sheets)

Runs on Railway.app and saves data to Google Sheets instead of local CSV.
No local files needed - all data goes to your Google Sheet.

Setup:
1. Create a Google Cloud project at console.cloud.google.com
2. Enable "Google Sheets API"
3. Create a Service Account (APIs & Services > Credentials > Create Credentials)
4. Download the JSON key file
5. Create a Google Sheet and share it with the service account email
6. Set environment variables in Railway (see below)

Environment Variables (set in Railway dashboard):
- GOOGLE_SHEETS_CREDS: The entire JSON content of your service account key
- SPREADSHEET_ID: The ID from your Google Sheet URL
  (e.g., from https://docs.google.com/spreadsheets/d/ABC123xyz/edit -> ABC123xyz)
"""

import os
import time
import json
from datetime import datetime, timezone
import requests

# Google Sheets
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    print("WARNING: gspread not installed. Run: pip install gspread")

KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"
SERIES_TICKER = "KXBTC15M"


def get_btc_price():
    """Get current BTC price from Kraken (real-time, closest to CF Benchmarks)"""
    try:
        resp = requests.get(
            "https://api.kraken.com/0/public/Ticker",
            params={"pair": "XBTUSD"},
            timeout=5
        )
        resp.raise_for_status()
        data = resp.json()
        # Kraken returns last trade price in 'c' field (first element)
        return float(data['result']['XXBTZUSD']['c'][0])
    except Exception as e:
        print(f"[BTC PRICE ERROR] {e}")
        return None


# Sheet names
PRICE_SHEET = "price_log"
RESULTS_SHEET = "window_results"


class GoogleSheetsLogger:
    def __init__(self):
        self.client = None
        self.spreadsheet = None
        self.price_sheet = None
        self.results_sheet = None
        self._connect()

    def _connect(self):
        if not GSPREAD_AVAILABLE:
            print("Google Sheets not available - gspread not installed")
            return

        creds_json = os.environ.get('GOOGLE_SHEETS_CREDS')
        spreadsheet_id = os.environ.get('SPREADSHEET_ID')

        if not creds_json or not spreadsheet_id:
            print("Missing GOOGLE_SHEETS_CREDS or SPREADSHEET_ID environment variables")
            print("Set these in your Railway dashboard")
            return

        try:
            creds_dict = json.loads(creds_json)
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            self.client = gspread.authorize(creds)
            self.spreadsheet = self.client.open_by_key(spreadsheet_id)

            # Get or create sheets
            self.price_sheet = self._get_or_create_sheet(PRICE_SHEET, [
                'timestamp', 'ticker', 'strike_price', 'btc_price', 'mins_left',
                'yes_ask', 'no_ask', 'yes_bid', 'no_bid',
                'yes_depth_1', 'yes_depth_3', 'yes_depth_all',
                'no_depth_1', 'no_depth_3', 'no_depth_all',
                'yes_levels', 'no_levels', 'spread'
            ])

            self.results_sheet = self._get_or_create_sheet(RESULTS_SHEET, [
                'timestamp', 'ticker', 'strike_price', 'result',
                'final_yes_price', 'final_no_price'
            ])

            print(f"Connected to Google Sheet: {self.spreadsheet.title}")

        except Exception as e:
            print(f"Failed to connect to Google Sheets: {e}")
            self.client = None

    def _get_or_create_sheet(self, name, headers):
        try:
            sheet = self.spreadsheet.worksheet(name)
        except gspread.WorksheetNotFound:
            sheet = self.spreadsheet.add_worksheet(title=name, rows=10000, cols=len(headers))
            sheet.append_row(headers)
            print(f"Created sheet: {name}")
        return sheet

    def is_connected(self):
        return self.client is not None and self.spreadsheet is not None

    def log_price(self, ticker, strike, btc_price, mins_left, market, orderbook):
        if not self.price_sheet:
            return False

        yes_ask = market.get('yes_ask', 0)
        no_ask = market.get('no_ask', 0)
        yes_bid = market.get('yes_bid', 0)
        no_bid = market.get('no_bid', 0)
        spread = abs(yes_ask - (100 - no_ask))

        row = [
            datetime.now().isoformat(),
            ticker,
            strike,
            btc_price or 0,
            round(mins_left, 1),
            yes_ask,
            no_ask,
            yes_bid,
            no_bid,
            orderbook.get('yes_depth_1', 0) if orderbook else 0,
            orderbook.get('yes_depth_3', 0) if orderbook else 0,
            orderbook.get('yes_depth_all', 0) if orderbook else 0,
            orderbook.get('no_depth_1', 0) if orderbook else 0,
            orderbook.get('no_depth_3', 0) if orderbook else 0,
            orderbook.get('no_depth_all', 0) if orderbook else 0,
            orderbook.get('yes_levels', 0) if orderbook else 0,
            orderbook.get('no_levels', 0) if orderbook else 0,
            spread
        ]

        try:
            self.price_sheet.append_row(row, value_input_option='RAW')
            return True
        except Exception as e:
            print(f"Failed to log price: {e}")
            return False

    def log_result(self, ticker, strike, result, final_yes, final_no):
        if not self.results_sheet:
            return False

        row = [
            datetime.now().isoformat(),
            ticker,
            strike,
            result,
            final_yes,
            final_no
        ]

        try:
            self.results_sheet.append_row(row, value_input_option='RAW')
            return True
        except Exception as e:
            print(f"Failed to log result: {e}")
            return False


def api_get(endpoint, params=None):
    try:
        resp = requests.get(f"{KALSHI_API}/{endpoint}", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[API ERROR] {e}")
        return None


def get_active_market():
    data = api_get("events", {"series_ticker": SERIES_TICKER, "status": "open"})
    if not data or not data.get('events'):
        return None
    event = data['events'][0]
    markets = api_get("markets", {"event_ticker": event['event_ticker']})
    if not markets or not markets.get('markets'):
        return None
    return markets['markets'][0]


def get_market_details(ticker):
    data = api_get(f"markets/{ticker}")
    return data.get('market') if data else None


def get_orderbook(ticker):
    data = api_get(f"markets/{ticker}/orderbook")
    if not data:
        return None

    orderbook = data.get('orderbook', {})
    yes_bids = orderbook.get('yes', [])
    no_bids = orderbook.get('no', [])

    return {
        'yes_best_price': yes_bids[0][0] if yes_bids else 0,
        'yes_depth_1': yes_bids[0][1] if len(yes_bids) > 0 else 0,
        'yes_depth_3': sum(level[1] for level in yes_bids[:3]) if yes_bids else 0,
        'yes_depth_all': sum(level[1] for level in yes_bids) if yes_bids else 0,
        'yes_levels': len(yes_bids),
        'no_best_price': no_bids[0][0] if no_bids else 0,
        'no_depth_1': no_bids[0][1] if len(no_bids) > 0 else 0,
        'no_depth_3': sum(level[1] for level in no_bids[:3]) if no_bids else 0,
        'no_depth_all': sum(level[1] for level in no_bids) if no_bids else 0,
        'no_levels': len(no_bids),
    }


def get_settled_markets():
    data = api_get("markets", {"series_ticker": SERIES_TICKER, "status": "settled", "limit": 20})
    return data.get('markets', []) if data else []


def mins_until_close(close_time_str):
    if not close_time_str:
        return None
    try:
        close = datetime.fromisoformat(close_time_str.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        return (close - now).total_seconds() / 60
    except:
        return None


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def run():
    print("=" * 70)
    print("KALSHI DATA LOGGER - Cloud Version (Google Sheets)")
    print("=" * 70)
    print(f"Series: {SERIES_TICKER} (Bitcoin 15-minute markets)")
    print("=" * 70)

    # Initialize Google Sheets
    sheets = GoogleSheetsLogger()

    if not sheets.is_connected():
        print("\nERROR: Could not connect to Google Sheets!")
        print("Make sure you have set these environment variables:")
        print("  - GOOGLE_SHEETS_CREDS: Full JSON content of service account key")
        print("  - SPREADSHEET_ID: ID from your Google Sheet URL")
        print("\nExiting...")
        return

    print("Connected to Google Sheets!")
    print("=" * 70 + "\n")

    last_ticker = None
    last_log_minute = None
    settled_tickers = set()

    windows_logged = 0
    snapshots_logged = 0

    while True:
        try:
            # Check for settlements
            settled = get_settled_markets()
            for market in settled:
                ticker = market.get('ticker')
                if ticker and ticker not in settled_tickers:
                    result = market.get('result')
                    if result:
                        strike = market.get('floor_strike', 0)
                        final_yes = 100 if result == 'yes' else 0
                        final_no = 100 if result == 'no' else 0

                        if sheets.log_result(ticker, strike, result, final_yes, final_no):
                            settled_tickers.add(ticker)
                            windows_logged += 1
                            outcome = "UP (YES)" if result == 'yes' else "DOWN (NO)"
                            log(f"SETTLED: {ticker} -> {outcome}")

            # Get current market
            market = get_active_market()
            if not market:
                time.sleep(30)
                continue

            details = get_market_details(market['ticker'])
            if not details:
                time.sleep(10)
                continue

            ticker = details['ticker']
            mins_left = mins_until_close(details.get('close_time'))

            if mins_left is None or mins_left < -1:
                time.sleep(10)
                continue

            # New window
            if ticker != last_ticker:
                strike = details.get('floor_strike', 0)
                log(f"NEW WINDOW: {ticker} | Strike: ${strike:,.2f}")
                last_ticker = ticker
                last_log_minute = None

            # Log pricing
            current_minute = int(mins_left)
            should_log = False

            if mins_left > 5:
                if current_minute != last_log_minute:
                    should_log = True
            else:
                should_log = True

            if should_log and mins_left >= 0:
                strike = details.get('floor_strike', 0)
                btc_price = get_btc_price()
                orderbook = get_orderbook(ticker)

                if sheets.log_price(ticker, strike, btc_price, mins_left, details, orderbook):
                    snapshots_logged += 1

                yes = details.get('yes_ask', 0)
                no = details.get('no_ask', 0)

                depth_str = ""
                if orderbook:
                    depth = orderbook['yes_depth_3'] if yes > no else orderbook['no_depth_3']
                    depth_str = f" | Depth: {depth}"

                btc_str = f" | BTC: ${btc_price:,.2f}" if btc_price else ""
                above_below = ""
                if btc_price and strike:
                    above_below = " (ABOVE)" if btc_price > strike else " (BELOW)"

                log(f"{mins_left:.1f}m | YES:{yes}c NO:{no}c{depth_str}{btc_str}{above_below} | Total: {snapshots_logged}")
                last_log_minute = current_minute

            # Adaptive sleep
            if mins_left > 12:
                time.sleep(30)
            elif mins_left > 5:
                time.sleep(15)
            elif mins_left > 1:
                time.sleep(10)
            else:
                time.sleep(5)

        except KeyboardInterrupt:
            print("\n\nStopping logger...")
            print(f"Total windows logged: {windows_logged}")
            print(f"Total price snapshots: {snapshots_logged}")
            break
        except Exception as e:
            log(f"ERROR: {e}")
            time.sleep(30)


if __name__ == "__main__":
    run()
