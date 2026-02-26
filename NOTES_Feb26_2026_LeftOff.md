# Strategy Notes - February 26, 2026

**Status:** Cloud logger running on Railway, collecting real Kalshi data to Google Sheets 24/7.

---

## Where We Left Off

The data collection problem is solved. Now we need to figure out if there's actually money here.

---

## The Big Questions We Need to Answer

### 1. Optimal Entry Time (Year Backtest)
- Test all entry times: 10m, 9m, 8m, 7m, 6m, 5m, 4m, 3m
- Don't throw out late entries - understand the full picture
- What's the win rate at each interval?
- Is 7 minutes actually the sweet spot or just where we stopped looking?

### 2. Price Availability Analysis (Live Data)
- What % of the time is there a "good" price (55-75c) at each time interval?
- 7 minutes left? 8 minutes? 5 minutes?
- How fast do prices move from tradeable to untradeable?
- Today's observation: prices hit 85-99c fast, good prices disappeared early

### 3. Depth/Liquidity Patterns
- Does depth correlate with high odds (confident market)?
- Or is it purely time-related (always thin near close)?
- At what point does liquidity become too thin to execute?
- Observation: ~0 depth past 3 minutes, bad prices at 4 minutes

### 4. Dynamic Bet Sizing
- Can we size based on edge? (bigger bets at 60c vs 70c)
- Martingale potential? (dangerous but high win rate might support it)
- What about tiny bets at 99c? (almost free money if it hits)
- Need to model bankroll requirements and risk of ruin

### 5. A/B/C Strategy Backtests
- Strategy A: Flat betting, 7min entry, 55-75c filter
- Strategy B: Dynamic sizing based on price
- Strategy C: Martingale with stop-loss
- **Priority: Test with REAL Kalshi prices first**, then validate against year data

---

## Data We're Collecting (Railway → Google Sheets)

- **96 windows per day** (every 15 min × 24 hours)
- Price snapshots at every minute (14m down to 0m)
- Order book depth at each snapshot
- Settlement results (YES/NO)
- After 1 week: ~672 windows with full price evolution

---

## Honest Assessment (Claude's Take)

**The Good:**
- 70% win rate at 7 minutes appears real from paper trading
- Momentum strategy is simple and doesn't require prediction
- Edge exists in the 55-75c price range mathematically
- Now we have real data to validate instead of guessing

**The Concerning:**
- Good prices (55-75c) seem to disappear fast - often by 7-8 minutes prices are already 85c+
- At 85c+ you need 91%+ win rate to profit - that's extremely tight
- Liquidity dries up near close - execution risk
- Kalshi's 7% fee eats into thin edges

**The Honest Answer on Money:**

| Scenario | Daily Potential | Reality Check |
|----------|-----------------|---------------|
| Best case | $100-300/day | Requires perfect execution, good prices available, no losing streaks |
| Realistic | $20-50/day | Some windows untradeable, normal variance, occasional losses |
| Worst case | -$200/day | Bad streak + martingale = account blow-up |

This is **grind money, not get-rich money**. If it works, it's a side income that runs itself. The question is whether the edge is consistent enough after fees and slippage.

**My honest take:** There's probably *something* here, but it's smaller than the paper trading suggested. The real prices we saw today moved fast. The 70% win rate might hold, but if you can only trade 30% of windows (because prices are bad), your actual opportunities shrink.

Worth pursuing with real data. Not worth quitting your job for.

---

## Next Steps (When You Return)

1. Let logger run for a few days
2. Analyze: What % of windows have tradeable prices at 7min?
3. Run year backtest with refined parameters
4. Build strategy simulator with real price data
5. Paper trade one more week with strict rules before real money

---

## Quick Links

- **Google Sheet:** Check your "Kalshi BTC 15 Minute Data" sheet
- **Railway Dashboard:** railway.app (logger running as "worker")
- **Code:** `15-minute-tester/` folder

---

*Go to work. The robot's collecting data. We'll know more in a week.*
