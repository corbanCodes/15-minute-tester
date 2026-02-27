#!/usr/bin/env python3
"""
PAPER TRADER - Winning Strategy
================================
Strategy: Buy NO when BTC is BELOW strike at 9 min or 5 min left

Tracks:
- Entry conditions
- Would-be trades
- Theoretical P&L with real Kalshi fees (7%)
"""

import os
import time
import json
from datetime import datetime, timezone
import requests

KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"
SERIES_TICKER = "KXBTC15M"

# Strategy parameters
BET_SIZE = 10  # $10 per trade for paper trading
ENTRY_MINUTES = [9, 5]  # Enter at 9 min or 5 min left

# Track trades
paper_trades = []
balance = 1000  # Starting paper balance

def kalshi_fee(price_cents):
    """Calculate Kalshi 7% fee"""
    if price_cents <= 0 or price_cents >= 100:
        return 0
    p = price_cents / 100
    return 0.07 * p * (1 - p) * 100

def get_btc_price():
    try:
        resp = requests.get("https://api.kraken.com/0/public/Ticker", params={"pair": "XBTUSD"}, timeout=5)
        return float(resp.json()['result']['XXBTZUSD']['c'][0])
    except:
        return None

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

def mins_until_close(close_time_str):
    if not close_time_str:
        return None
    try:
        close = datetime.fromisoformat(close_time_str.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        return (close - now).total_seconds() / 60
    except:
        return None

def get_settled_markets():
    data = api_get("markets", {"series_ticker": SERIES_TICKER, "status": "settled", "limit": 20})
    return data.get('markets', []) if data else []

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def save_trades():
    """Save paper trades to CSV"""
    if not paper_trades:
        return

    with open('paper_trades.csv', 'w') as f:
        f.write('timestamp,ticker,strike,btc_price,mins_left,direction,entry_price,contracts,cost,fee,outcome,profit,balance\n')
        for t in paper_trades:
            f.write(f"{t['timestamp']},{t['ticker']},{t['strike']},{t['btc_price']},{t['mins_left']},{t['direction']},{t['entry_price']},{t['contracts']},{t['cost']:.2f},{t['fee']:.2f},{t['outcome']},{t['profit']:.2f},{t['balance']:.2f}\n")
    log(f"Saved {len(paper_trades)} trades to paper_trades.csv")

def run():
    global balance

    print("=" * 70)
    print("PAPER TRADER - WINNING STRATEGY")
    print("=" * 70)
    print(f"Strategy: Buy NO when BTC < strike at {ENTRY_MINUTES} min left")
    print(f"Bet size: ${BET_SIZE} per trade")
    print(f"Starting balance: ${balance}")
    print("=" * 70 + "\n")

    last_ticker = None
    traded_this_window = False
    pending_trades = {}  # ticker -> trade info
    settled_tickers = set()

    wins = 0
    losses = 0

    while True:
        try:
            # Check for settlements
            settled = get_settled_markets()
            for market in settled:
                ticker = market.get('ticker')
                if ticker and ticker in pending_trades and ticker not in settled_tickers:
                    result = market.get('result')
                    if result:
                        trade = pending_trades[ticker]

                        # NO wins if result is 'no'
                        no_wins = result == 'no'

                        if no_wins:
                            profit = trade['contracts'] - trade['cost'] - trade['fee']
                            wins += 1
                            status = "✓ WIN"
                        else:
                            profit = -trade['cost'] - trade['fee']
                            losses += 1
                            status = "✗ LOSS"

                        balance += profit

                        trade['outcome'] = 'win' if no_wins else 'loss'
                        trade['profit'] = profit
                        trade['balance'] = balance
                        paper_trades.append(trade)

                        settled_tickers.add(ticker)

                        log(f"{status}: {ticker} | NO @ {trade['entry_price']}c | Profit: ${profit:+.2f} | Balance: ${balance:.2f}")
                        log(f"   Stats: {wins}W / {losses}L ({wins/(wins+losses)*100:.0f}% win rate)")

                        save_trades()

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

            if mins_left is None or mins_left < 0:
                time.sleep(10)
                continue

            # New window - reset
            if ticker != last_ticker:
                strike = details.get('floor_strike', 0)
                log(f"\n{'='*50}")
                log(f"NEW WINDOW: {ticker}")
                log(f"Strike: ${strike:,.2f}")
                log(f"{'='*50}")
                last_ticker = ticker
                traded_this_window = False

            # Check entry conditions
            if not traded_this_window:
                btc_price = get_btc_price()
                strike = details.get('floor_strike', 0)
                no_ask = details.get('no_ask', 0)
                yes_ask = details.get('yes_ask', 0)

                # Check each entry minute
                for entry_min in ENTRY_MINUTES:
                    # Allow 30 second window around target minute
                    if entry_min - 0.5 <= mins_left <= entry_min + 0.5:
                        # Strategy: Buy NO when BTC is BELOW strike
                        if btc_price and btc_price < strike:
                            diff_pct = (btc_price - strike) / strike * 100

                            # Calculate trade
                            contracts = max(1, int(BET_SIZE / (no_ask / 100)))
                            cost = contracts * (no_ask / 100)
                            fee = kalshi_fee(no_ask) * contracts / 100

                            trade = {
                                'timestamp': datetime.now().isoformat(),
                                'ticker': ticker,
                                'strike': strike,
                                'btc_price': btc_price,
                                'mins_left': round(mins_left, 1),
                                'direction': 'NO',
                                'entry_price': no_ask,
                                'contracts': contracts,
                                'cost': cost,
                                'fee': fee,
                                'outcome': 'pending',
                                'profit': 0,
                                'balance': balance
                            }

                            pending_trades[ticker] = trade
                            traded_this_window = True

                            log(f"")
                            log(f"🎯 PAPER TRADE ENTERED!")
                            log(f"   Direction: NO (betting price stays below)")
                            log(f"   Entry: {mins_left:.1f} min left")
                            log(f"   BTC: ${btc_price:,.2f} ({diff_pct:.3f}% below strike)")
                            log(f"   NO price: {no_ask}c")
                            log(f"   Contracts: {contracts}")
                            log(f"   Cost: ${cost:.2f} + ${fee:.2f} fee")
                            log(f"")
                            break
                        else:
                            # BTC above strike - no trade
                            if btc_price:
                                diff_pct = (btc_price - strike) / strike * 100
                                log(f"⏭️  {mins_left:.1f}m: BTC ${btc_price:,.2f} is ABOVE strike ({diff_pct:+.3f}%) - NO TRADE")

            # Status update
            if mins_left > 0:
                btc_price = get_btc_price()
                strike = details.get('floor_strike', 0)
                no_ask = details.get('no_ask', 0)
                yes_ask = details.get('yes_ask', 0)

                if btc_price and strike:
                    position = "ABOVE ⬆️" if btc_price > strike else "BELOW ⬇️"
                    diff = btc_price - strike
                    trade_status = "📊 POSITION OPEN" if ticker in pending_trades and pending_trades[ticker]['outcome'] == 'pending' else ""

                    if int(mins_left) in [10, 9, 8, 7, 6, 5, 4, 3, 2, 1] or mins_left < 1:
                        log(f"{mins_left:.1f}m | YES:{yes_ask}c NO:{no_ask}c | BTC: ${btc_price:,.2f} ({position} by ${abs(diff):.2f}) {trade_status}")

            # Adaptive sleep
            if mins_left > 10:
                time.sleep(20)
            elif mins_left > 5:
                time.sleep(10)
            elif mins_left > 1:
                time.sleep(5)
            else:
                time.sleep(3)

        except KeyboardInterrupt:
            print("\n\n" + "=" * 70)
            print("PAPER TRADING SESSION ENDED")
            print("=" * 70)
            print(f"Total trades: {len(paper_trades)}")
            print(f"Wins: {wins} | Losses: {losses}")
            if wins + losses > 0:
                print(f"Win rate: {wins/(wins+losses)*100:.1f}%")
            print(f"Final balance: ${balance:.2f}")
            print(f"Profit/Loss: ${balance - 1000:+.2f}")
            save_trades()
            break
        except Exception as e:
            log(f"ERROR: {e}")
            time.sleep(30)


if __name__ == "__main__":
    run()
