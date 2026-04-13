# Polymarket Sports Betting Bot — Build Specification

## Goal
Build a fully autonomous Python bot that trades on Polymarket sports markets (NBA, NFL, NHL, tennis, etc.) using AI-driven predictions. The bot must run 24/7 with zero manual intervention.

## Architecture
Reference these cloned repos for patterns and code reuse:
- `_ref/agents/` — Official Polymarket agent framework (Gamma API, CLOB client, trade execution)
- `_ref/sports-ev-bot/` — XGBoost sports prediction engine (NBA/Tennis models, feature engineering)
- `_ref/poly-sports-bot/` — Fast Polymarket sports execution (WebSocket, market discovery)

Reuse as much as possible from these repos. Do NOT reinvent the wheel.

## Core Components

### 1. Market Discovery (`src/market_scanner.py`)
- Use Gamma API to find live sports markets on Polymarket
- Filter for: NBA, NFL, NHL, MLB, tennis, soccer, UFC
- Auto-detect market type (moneyline, spread, totals, player props)
- Track market expiry and switch to next available markets
- Parse market questions to extract: sport, teams/players, bet type, line

### 2. Data Pipeline (`src/data_pipeline.py`)
- Fetch live odds from multiple sources:
  - the-odds-api.com (free tier, FanDuel/DraftKings odds)
  - PrizePicks partner API (player prop lines)
  - ESPN API for injury reports and lineup changes
- Cache data with TTL (avoid API rate limits)
- Normalize odds across sources (American → implied probability)
- Remove vig from bookmaker odds to get true probabilities

### 3. Prediction Engine (`src/predictor.py`)
- XGBoost models for major sports (start with NBA and NFL)
- Features: historical stats, opponent strength, home/away, rest days, injuries, weather
- Use `the-odds-api` for historical odds data for training
- Output: predicted probability for each outcome + confidence score
- Fallback: if no model trained yet, use implied probability from bookmaker odds

### 4. Value Detector (`src/value_detector.py`)
- Compare our predicted probability vs Polymarket price
- Calculate edge: `our_probability - market_price`
- Only trade when edge exceeds minimum threshold (default: 5%)
- Adjust for market liquidity (skip thin markets)
- Rank opportunities by expected value

### 5. Trade Executor (`src/executor.py`)
- Use Polymarket CLOB client from `_ref/agents/` for order execution
- Place limit orders at favorable prices
- Position sizing based on Kelly criterion (fractional, default 25% Kelly)
- Max position size cap (default: 5 USDC per trade)
- Track fills and positions
- Auto-cancel unfilled orders after timeout

### 6. Risk Management (`src/risk_manager.py`)
- Daily loss limit: $3.00 USDC (circuit breaker, halts all trading)
- Max concurrent positions: 5
- Max exposure per sport: $10 USDC
- No trading in last 5 minutes before market expiry
- Cooldown: 60 seconds between trades on same market
- Track daily P&L with reset at midnight UTC

### 7. Notification System (`src/notifier.py`)
- Push notifications via ntfy.sh (no API key needed)
- Alert on: trade opened, trade closed (win/loss), circuit breaker tripped, error
- Daily summary: trades, P&L, win rate, active positions

### 8. Main Loop (`main.py`)
- Async event loop running all components
- Health checks every 60 seconds
- Auto-reconnect on WebSocket/API failures
- Graceful shutdown on Ctrl+C
- State persistence (survive restarts)

## Config (`config.yaml`)
```yaml
polymarket:
  safe_address: ""  # set via env var
  clob_host: "https://clob.polymarket.com"
  chain_id: 137

sports:
  enabled:
    - NBA
    - NFL
    - NHL
    - tennis
  min_edge: 0.05  # 5% minimum edge to trade

risk:
  daily_loss_limit: 3.00
  max_positions: 5
  max_per_sport: 10.00
  kelly_fraction: 0.25
  max_bet_size: 5.00
  cooldown_seconds: 60
  no_trade_before_expiry_minutes: 5

data:
  odds_api_key: ""  # the-odds-api.com free key
  cache_ttl_seconds: 30

notifications:
  ntfy_topic: "poly-sports-bot"
  enabled: true

logging:
  level: "INFO"
  file: "logs/bot.log"
```

## Requirements
- Python 3.10+
- asyncio + aiohttp for async HTTP
- websockets for real-time data
- xgboost for prediction models
- pandas for data handling
- pyyaml for config
- python-dotenv for env vars
- requests (fallback sync HTTP)

## Critical Rules
1. MUST be fully autonomous — zero manual intervention once started
2. MUST have circuit breaker — daily loss limit with hard stop
3. MUST log all decisions — audit trail for every trade
4. MUST persist state — survive bot restarts without losing position data
5. MUST handle API failures gracefully — retry with backoff, never crash
6. NEVER risk more than max_bet_size per trade
7. NEVER trade markets with less than $100 liquidity on both sides

## File Structure
```
polymarket-sports-bot/
├── main.py                  # Entry point
├── config.yaml              # Config template
├── requirements.txt         # Dependencies
├── src/
│   ├── __init__.py
│   ├── market_scanner.py    # Gamma API sports market discovery
│   ├── data_pipeline.py     # Multi-source odds/data fetching
│   ├── predictor.py         # XGBoost prediction models
│   ├── value_detector.py    # Edge calculation
│   ├── executor.py          # Polymarket order execution
│   ├── risk_manager.py      # Position sizing + limits
│   ├── notifier.py          # ntfy.sh push notifications
│   ├── gamma_client.py      # Polymarket Gamma API wrapper
│   ├── clob_client.py       # Polymarket CLOB API wrapper
│   └── state.py             # Persistent state management
├── models/                  # Trained XGBoost models (gitignored)
├── data/                    # Cached data (gitignored)
├── logs/                    # Log files (gitignored)
└── tests/                   # Unit tests
```

## Environment Variables (set at runtime, not in code)
- `POLY_PRIVATE_KEY` — Polymarket wallet private key
- `POLY_SAFE_ADDRESS` — Polymarket Safe address
- `ODDS_API_KEY` — the-odds-api.com API key (free tier)

## First Run Behavior
On first run with no trained models:
1. Use bookmaker implied probabilities as baseline predictions
2. Start in paper trading mode (log trades but don't execute)
3. After 50 paper trades, show performance stats
4. Auto-switch to live trading when confidence metrics are met
5. Begin training XGBoost models from collected data

When completely finished, run this command to notify me:
openclaw system event --text "Done: Polymarket sports betting bot fully built" --mode now
