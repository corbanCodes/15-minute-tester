#!/usr/bin/env python3
"""
KALSHI HIGH-FREQUENCY DATA LOGGER
=================================
Second-by-second logging for comprehensive simulation data.

Captures EVERYTHING:
- BTC price from Binance (fastest)
- All Kalshi market data
- Full orderbook depth
- Timestamps with milliseconds

Setup:
1. Share your Google Sheet with the service account email
2. Set environment variables in Railway:
   - GOOGLE_SHEETS_CREDS: JSON content of service account key
   - HF_SPREADSHEET_ID: ID from your Google Sheet URL for HF data
"""

import os
import time
import json
from datetime import datetime, timezone
import requests
from threading import Thread
from collections import deque

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

# Binance is faster than Kraken
BINANCE_API = "https://api.binance.us/api/v3"


def get_btc_price_binance():
    """Get BTC price from Binance (fastest, ~50ms)"""
    try:
        resp = requests.get(
            f"{BINANCE_API}/ticker/price",
            params={"symbol": "BTCUSDT"},
            timeout=2
        )
        resp.raise_for_status()
        return float(resp.json()['price'])
    except Exception as e:
        return None


def get_btc_price_kraken():
    """Fallback: Get BTC price from Kraken"""
    try:
        resp = requests.get(
            "https://api.kraken.com/0/public/Ticker",
            params={"pair": "XBTUSD"},
            timeout=3
        )
        resp.raise_for_status()
        return float(resp.json()['result']['XXBTZUSD']['c'][0])
    except:
        return None


def get_btc_price():
    """Try Binance first, fallback to Kraken"""
    price = get_btc_price_binance()
    if price is None:
        price = get_btc_price_kraken()
    return price


class GoogleSheetsHFLogger:
    """High-frequency logger with batching to avoid rate limits"""

    def __init__(self):
        self.client = None
        self.spreadsheet = None
        self.tick_sheet = None
        self.window_sheet = None
        self.summary_sheet = None
        self.batch_queue = deque(maxlen=1000)
        self.last_flush = time.time()
        self.FLUSH_INTERVAL = 5  # Flush every 5 seconds
        self.BATCH_SIZE = 50  # Max rows per flush
        self._connect()

    def _connect(self):
        if not GSPREAD_AVAILABLE:
            print("Google Sheets not available - gspread not installed")
            return

        creds_json = os.environ.get('GOOGLE_SHEETS_CREDS')
        spreadsheet_id = os.environ.get('SPREADSHEET_ID_SECOND_BY_SECOND')

        if not creds_json or not spreadsheet_id:
            print("Missing GOOGLE_SHEETS_CREDS or SPREADSHEET_ID_SECOND_BY_SECOND environment variables")
            return

        try:
            creds_dict = json.loads(creds_json)
            print(f"Service account email: {creds_dict.get('client_email', 'NOT FOUND')}")

            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            self.client = gspread.authorize(creds)
            self.spreadsheet = self.client.open_by_key(spreadsheet_id)

            # Create sheets for different data types
            self.tick_sheet = self._get_or_create_sheet('tick_data', [
                'timestamp_utc', 'timestamp_local', 'epoch_ms',
                'ticker', 'window_id', 'strike_price',
                'secs_left', 'mins_left',
                'btc_price', 'btc_vs_strike', 'btc_diff_pct',
                'yes_ask', 'yes_bid', 'no_ask', 'no_bid',
                'mid_price', 'spread',
                'yes_depth_1c', 'yes_depth_3c', 'yes_depth_5c', 'yes_depth_all',
                'no_depth_1c', 'no_depth_3c', 'no_depth_5c', 'no_depth_all',
                'yes_levels', 'no_levels',
                'total_volume', 'last_trade_price', 'last_trade_side'
            ])

            self.window_sheet = self._get_or_create_sheet('window_results', [
                'timestamp', 'ticker', 'window_id',
                'strike_price', 'open_btc', 'close_btc',
                'result', 'result_direction',
                'open_yes_price', 'close_yes_price',
                'open_no_price', 'close_no_price',
                'price_swing_high', 'price_swing_low',
                'total_ticks_logged'
            ])

            self.summary_sheet = self._get_or_create_sheet('session_summary', [
                'session_start', 'session_end', 'duration_hours',
                'windows_tracked', 'ticks_logged',
                'yes_wins', 'no_wins',
                'avg_yes_open_price', 'avg_no_open_price'
            ])

            print(f"Connected to Google Sheet: {self.spreadsheet.title}")

        except Exception as e:
            print(f"Failed to connect to Google Sheets: {e}")
            import traceback
            traceback.print_exc()
            self.client = None

    def _get_or_create_sheet(self, name, headers):
        try:
            sheet = self.spreadsheet.worksheet(name)
        except gspread.WorksheetNotFound:
            sheet = self.spreadsheet.add_worksheet(title=name, rows=100000, cols=len(headers))
            sheet.append_row(headers)
            print(f"Created sheet: {name}")
        return sheet

    def is_connected(self):
        return self.client is not None and self.spreadsheet is not None

    def queue_tick(self, data):
        """Add tick to queue for batch writing"""
        self.batch_queue.append(data)

        # Flush if interval passed or batch is full
        if time.time() - self.last_flush > self.FLUSH_INTERVAL or len(self.batch_queue) >= self.BATCH_SIZE:
            self._flush_batch()

    def _flush_batch(self):
        """Write queued ticks to sheet"""
        if not self.tick_sheet or not self.batch_queue:
            return

        rows = []
        while self.batch_queue and len(rows) < self.BATCH_SIZE:
            rows.append(list(self.batch_queue.popleft().values()))

        if rows:
            try:
                self.tick_sheet.append_rows(rows, value_input_option='RAW')
                self.last_flush = time.time()
            except Exception as e:
                print(f"Failed to flush batch: {e}")

    def log_tick(self, ticker, strike, btc_price, secs_left, market, orderbook):
        """Queue a tick for logging"""
        now = datetime.now(timezone.utc)
        now_local = datetime.now()

        yes_ask = market.get('yes_ask', 0)
        no_ask = market.get('no_ask', 0)
        yes_bid = market.get('yes_bid', 0)
        no_bid = market.get('no_bid', 0)

        mid_price = (yes_ask + (100 - no_ask)) / 2 if yes_ask and no_ask else 0
        spread = abs(yes_ask - (100 - no_ask))

        btc_vs_strike = "ABOVE" if btc_price and btc_price > strike else "BELOW" if btc_price else "UNKNOWN"
        btc_diff_pct = ((btc_price - strike) / strike * 100) if btc_price and strike else 0

        # Extract window ID from ticker (e.g., KXBTC15M-26FEB261430-30 -> 26FEB261430)
        window_id = ticker.split('-')[1] if '-' in ticker else ticker

        tick_data = {
            'timestamp_utc': now.isoformat(),
            'timestamp_local': now_local.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
            'epoch_ms': int(now.timestamp() * 1000),
            'ticker': ticker,
            'window_id': window_id,
            'strike_price': strike,
            'secs_left': round(secs_left, 1),
            'mins_left': round(secs_left / 60, 2),
            'btc_price': btc_price or 0,
            'btc_vs_strike': btc_vs_strike,
            'btc_diff_pct': round(btc_diff_pct, 4),
            'yes_ask': yes_ask,
            'yes_bid': yes_bid,
            'no_ask': no_ask,
            'no_bid': no_bid,
            'mid_price': round(mid_price, 1),
            'spread': spread,
            'yes_depth_1c': orderbook.get('yes_depth_1', 0) if orderbook else 0,
            'yes_depth_3c': orderbook.get('yes_depth_3', 0) if orderbook else 0,
            'yes_depth_5c': orderbook.get('yes_depth_5', 0) if orderbook else 0,
            'yes_depth_all': orderbook.get('yes_depth_all', 0) if orderbook else 0,
            'no_depth_1c': orderbook.get('no_depth_1', 0) if orderbook else 0,
            'no_depth_3c': orderbook.get('no_depth_3', 0) if orderbook else 0,
            'no_depth_5c': orderbook.get('no_depth_5', 0) if orderbook else 0,
            'no_depth_all': orderbook.get('no_depth_all', 0) if orderbook else 0,
            'yes_levels': orderbook.get('yes_levels', 0) if orderbook else 0,
            'no_levels': orderbook.get('no_levels', 0) if orderbook else 0,
            'total_volume': market.get('volume', 0),
            'last_trade_price': market.get('last_price', 0),
            'last_trade_side': market.get('result', '')
        }

        self.queue_tick(tick_data)
        return True

    def log_window_result(self, ticker, strike, result, window_data):
        """Log final window result"""
        if not self.window_sheet:
            return False

        window_id = ticker.split('-')[1] if '-' in ticker else ticker

        row = [
            datetime.now().isoformat(),
            ticker,
            window_id,
            strike,
            window_data.get('open_btc', 0),
            window_data.get('close_btc', 0),
            result,
            "UP" if result == 'yes' else "DOWN",
            window_data.get('open_yes', 0),
            window_data.get('close_yes', 0),
            window_data.get('open_no', 0),
            window_data.get('close_no', 0),
            window_data.get('btc_high', 0),
            window_data.get('btc_low', 0),
            window_data.get('ticks', 0)
        ]

        try:
            self.window_sheet.append_row(row, value_input_option='RAW')
            return True
        except Exception as e:
            print(f"Failed to log window: {e}")
            return False

    def flush(self):
        """Force flush any remaining data"""
        self._flush_batch()


def api_get(endpoint, params=None):
    try:
        resp = requests.get(f"{KALSHI_API}/{endpoint}", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
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

    def depth_within_cents(bids, cents):
        """Sum liquidity within X cents of best price"""
        if not bids:
            return 0
        best = bids[0][0]
        return sum(level[1] for level in bids if abs(level[0] - best) <= cents)

    return {
        'yes_best_price': yes_bids[0][0] if yes_bids else 0,
        'yes_depth_1': depth_within_cents(yes_bids, 1),
        'yes_depth_3': depth_within_cents(yes_bids, 3),
        'yes_depth_5': depth_within_cents(yes_bids, 5),
        'yes_depth_all': sum(level[1] for level in yes_bids) if yes_bids else 0,
        'yes_levels': len(yes_bids),
        'no_best_price': no_bids[0][0] if no_bids else 0,
        'no_depth_1': depth_within_cents(no_bids, 1),
        'no_depth_3': depth_within_cents(no_bids, 3),
        'no_depth_5': depth_within_cents(no_bids, 5),
        'no_depth_all': sum(level[1] for level in no_bids) if no_bids else 0,
        'no_levels': len(no_bids),
    }


def get_settled_markets():
    data = api_get("markets", {"series_ticker": SERIES_TICKER, "status": "settled", "limit": 20})
    return data.get('markets', []) if data else []


def secs_until_close(close_time_str):
    if not close_time_str:
        return None
    try:
        close = datetime.fromisoformat(close_time_str.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        return (close - now).total_seconds()
    except:
        return None


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {msg}", flush=True)


def run():
    print("=" * 70)
    print("KALSHI HIGH-FREQUENCY DATA LOGGER")
    print("=" * 70)
    print(f"Series: {SERIES_TICKER} (Bitcoin 15-minute markets)")
    print("Logging: Every second when possible")
    print("=" * 70)

    # Initialize Google Sheets
    sheets = GoogleSheetsHFLogger()

    if not sheets.is_connected():
        print("\nERROR: Could not connect to Google Sheets!")
        print("Make sure you have set these environment variables:")
        print("  - GOOGLE_SHEETS_CREDS: Full JSON content of service account key")
        print("  - SPREADSHEET_ID_SECOND_BY_SECOND: ID from your Google Sheet URL")
        print("\nExiting...")
        return

    print("\nConnected! Starting high-frequency logging...")
    print("=" * 70 + "\n")

    last_ticker = None
    settled_tickers = set()

    # Window tracking
    window_data = {}
    ticks_this_window = 0
    total_ticks = 0
    windows_completed = 0

    session_start = datetime.now()

    while True:
        try:
            loop_start = time.time()

            # Check for settlements
            settled = get_settled_markets()
            for market in settled:
                ticker = market.get('ticker')
                if ticker and ticker not in settled_tickers:
                    result = market.get('result')
                    if result:
                        strike = market.get('floor_strike', 0)

                        if ticker in window_data:
                            wd = window_data[ticker]
                            wd['close_btc'] = get_btc_price()
                            sheets.log_window_result(ticker, strike, result, wd)
                            del window_data[ticker]

                        settled_tickers.add(ticker)
                        windows_completed += 1
                        outcome = "UP (YES)" if result == 'yes' else "DOWN (NO)"
                        log(f"🏁 SETTLED: {ticker} -> {outcome} | Windows: {windows_completed}")

            # Get current market
            market = get_active_market()
            if not market:
                time.sleep(1)
                continue

            details = get_market_details(market['ticker'])
            if not details:
                time.sleep(0.5)
                continue

            ticker = details['ticker']
            secs_left = secs_until_close(details.get('close_time'))

            if secs_left is None or secs_left < -60:
                time.sleep(1)
                continue

            # New window
            if ticker != last_ticker:
                strike = details.get('floor_strike', 0)
                btc_price = get_btc_price()

                log(f"\n{'='*50}")
                log(f"🆕 NEW WINDOW: {ticker}")
                log(f"   Strike: ${strike:,.2f} | BTC: ${btc_price:,.2f}")
                log(f"{'='*50}")

                last_ticker = ticker
                ticks_this_window = 0

                # Initialize window tracking
                window_data[ticker] = {
                    'open_btc': btc_price,
                    'close_btc': btc_price,
                    'btc_high': btc_price,
                    'btc_low': btc_price,
                    'open_yes': details.get('yes_ask', 0),
                    'open_no': details.get('no_ask', 0),
                    'close_yes': 0,
                    'close_no': 0,
                    'ticks': 0
                }

            # Log tick if window is active
            if secs_left >= 0:
                strike = details.get('floor_strike', 0)
                btc_price = get_btc_price()
                orderbook = get_orderbook(ticker)

                sheets.log_tick(ticker, strike, btc_price, secs_left, details, orderbook)
                ticks_this_window += 1
                total_ticks += 1

                # Update window data
                if ticker in window_data:
                    wd = window_data[ticker]
                    if btc_price:
                        wd['close_btc'] = btc_price
                        wd['btc_high'] = max(wd['btc_high'], btc_price)
                        wd['btc_low'] = min(wd['btc_low'], btc_price)
                    wd['close_yes'] = details.get('yes_ask', 0)
                    wd['close_no'] = details.get('no_ask', 0)
                    wd['ticks'] = ticks_this_window

                # Status update
                yes = details.get('yes_ask', 0)
                no = details.get('no_ask', 0)
                mins = secs_left / 60

                above_below = "⬆️" if btc_price and btc_price > strike else "⬇️"
                diff = abs(btc_price - strike) if btc_price else 0

                # Log every 10 ticks or at key moments
                if ticks_this_window % 10 == 0 or secs_left < 60 or mins > 14:
                    log(f"{mins:.1f}m | YES:{yes:2d}c NO:{no:2d}c | BTC: ${btc_price:,.2f} {above_below} (${diff:,.2f}) | Ticks: {ticks_this_window}")

            # Calculate sleep to maintain ~1 second intervals
            elapsed = time.time() - loop_start
            sleep_time = max(0.1, 1.0 - elapsed)
            time.sleep(sleep_time)

        except KeyboardInterrupt:
            print("\n\n" + "=" * 70)
            print("STOPPING HIGH-FREQUENCY LOGGER")
            print("=" * 70)

            # Flush remaining data
            sheets.flush()

            duration = (datetime.now() - session_start).total_seconds() / 3600
            print(f"Session duration: {duration:.2f} hours")
            print(f"Total ticks logged: {total_ticks:,}")
            print(f"Windows completed: {windows_completed}")
            print(f"Average ticks/window: {total_ticks/max(1,windows_completed):.0f}")
            break

        except Exception as e:
            log(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(5)


if __name__ == "__main__":
    run()
