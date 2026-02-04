# PolyArb 🔮

**Polymarket Alpha Extraction System**

> "Beat the market by understanding the players, not predicting the outcomes"

## Philosophy

Most traders try to predict events. That's gambling.

Smart money plays the players:
- **Detect bot patterns** → front-run their rebalancing
- **Exploit human psychology** → fade FOMO, buy panic
- **Find structural edges** → wide spreads, round number magnetism
- **Validate everything** → if it doesn't backtest, it doesn't trade

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     DATA LAYER                              │
│  collectors/polymarket_collector.py                         │
│  → Price snapshots every 60s                                │
│  → SQLite time-series database                              │
│  → Run 24/7 to build historical dataset                     │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   ANALYSIS LAYER                            │
│  analysis/player_analysis.py                                │
│  → Time-of-day patterns                                     │
│  → Bot detection (activity uniformity, price precision)     │
│  → Round number magnetism                                   │
│  → Mean reversion measurement                               │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  BACKTEST LAYER                             │
│  backtest/engine.py + strategies.py                         │
│  → Realistic fees (1%) and slippage (0.5%)                  │
│  → Risk metrics: Sharpe, Sortino, VaR, CVaR, Max DD         │
│  → BULLSHIT DETECTION:                                      │
│     • Curve fitting (Sharpe > 3 = suspicious)               │
│     • Pennies/steamroller (high win rate + huge losses)     │
│     • Statistical significance (need 30+ trades)            │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  EXECUTION LAYER                            │
│  (Paper trade first, always)                                │
│  → Only strategies that pass backtest validation            │
│  → Position sizing based on Kelly criterion                 │
│  → Risk limits enforced                                     │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Install
git clone https://github.com/spanishflu-est1918/polyarb.git
cd polyarb
pip install -r requirements.txt
npm install  # For the scanner

# Step 1: Start collecting data (run in background)
python main.py collect

# Step 2: Check status
python main.py status

# Step 3: Analyze patterns (after 24+ hours of data)
python main.py analyze

# Step 4: Backtest strategies
python main.py backtest

# Bonus: Quick market scan
python main.py scan
```

## Strategies Tested

| Strategy | Hypothesis | Reality Check |
|----------|------------|---------------|
| `basic_arb` | YES + NO < 1.0 = free money | Bots close these instantly |
| `mean_reversion` | Prices that spike revert | Sometimes works, needs data |
| `spread_capture` | Wide spreads = inefficiency | Requires market making infra |
| `momentum` | Winners keep winning | Usually LOSES in prediction markets |
| `bot_front_run` | Bots rebalance predictably | SPECULATIVE - our main thesis |

## Bullshit Detection

Every backtest is screened for:

### 1. Curve Fitting
```
Sharpe > 3.0 → Suspicious (real strategies rarely exceed 2.0)
Win rate > 80% with < 100 trades → Probably overfit
```

### 2. Pennies in Front of Steamroller
```
Win rate > 70% AND (avg_loss / avg_win) > 5 → DANGER
You're picking up nickels until a truck hits you
```

### 3. Statistical Significance
```
< 30 trades → Insufficient data
Need enough samples to distinguish skill from luck
```

## Output Example

```
╔══════════════════════════════════════════════════════════════════╗
║  BACKTEST RESULTS - ✅ VALID
╠══════════════════════════════════════════════════════════════════╣
║  RETURNS
║  ├─ Total Return: +12.34%
║  ├─ Sharpe Ratio: 1.45
║  ├─ Sortino Ratio: 2.10
║  └─ Calmar Ratio: 0.89
╠══════════════════════════════════════════════════════════════════╣
║  RISK (THIS IS WHAT MATTERS)
║  ├─ Max Drawdown: -13.87%
║  ├─ VaR 95%: -2.34%
║  ├─ CVaR 95%: -3.56%
║  └─ Worst Trade: -5.21%
╠══════════════════════════════════════════════════════════════════╣
║  BULLSHIT DETECTION
║  ├─ Curve Fitted: ✓ NO
║  ├─ Pennies/Steamroller: ✓ NO
║  └─ Sufficient Trades: ✓ YES
╚══════════════════════════════════════════════════════════════════╝
```

## Data Collection

The collector captures:
- **Price snapshots** (yes_price, no_price, spread) every 60s
- **Volume** (24h trading volume)
- **Liquidity** (order book depth)
- **Market metadata** (question, end date, outcomes)

Data is stored in SQLite at `data/polymarket.db`.

**Minimum recommended collection time:** 
- 24 hours for basic patterns
- 7 days for day-of-week effects
- 30 days for robust backtesting

## The Real Alpha

After extensive analysis, here's what actually might work:

1. **Weekend Inefficiency** - Lower bot activity = wider spreads = more edge
2. **Round Number Magnetism** - Prices cluster at 0.25/0.50/0.75
3. **News Lag** - Retail FOMO arrives 5-15 min after events
4. **Overreaction Decay** - Big moves partially revert in 1-4 hours

**What probably doesn't work:**
- Simple price arbitrage (bots are faster)
- Momentum (prediction markets mean-revert)
- Anything that sounds too easy

## Disclaimer

⚠️ **THIS IS FOR RESEARCH AND PAPER TRADING ONLY**

- Past performance doesn't guarantee future results
- Markets can stay irrational longer than you can stay solvent
- Backtest results include survivorship bias
- Real execution will be worse than simulation
- This is not financial advice

## License

MIT - Use at your own risk.

---

*"The market can remain irrational longer than you can remain solvent."* - Keynes

*"But with enough data, you can at least measure how irrational."* - PolyArb
