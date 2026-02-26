# Kalshi BTC 15-Minute Data Logger

Collects price and liquidity data from Kalshi's BTC 15-minute prediction markets. Runs 24/7 on Railway, saves to Google Sheets.

## What It Does

- Captures prices every minute (YES/NO ask/bid)
- Records order book depth (liquidity)
- Logs settlement results (which side won)
- Stores everything in Google Sheets for analysis

## Deploy to Railway

1. Push this repo to GitHub
2. Connect to Railway
3. Add environment variables:
   - `GOOGLE_SHEETS_CREDS` - Service account JSON contents
   - `SPREADSHEET_ID` - Your Google Sheet ID

See `RAILWAY_SETUP.md` for detailed instructions.

## Local Files (in archive/)

- `archive/analysis/` - Backtest and analysis scripts
- `archive/old_bots/` - Previous bot versions, paper traders
- `archive/presentations/` - Strategy presentations
- `archive/reference/` - Downloaded repos for reference
- `archive/historical_data/` - BTC price CSVs (2025-2026)

## Strategy Notes

- Entry: 7 minutes before close
- Price filter: 55-75c only (positive EV range)
- Bet WITH momentum (if YES > NO, bet YES)
- ~70% win rate at 7-minute entry based on paper trading
