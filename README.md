# Polymarket Sports Betting Bot

Fully autonomous sports trading bot for [Polymarket](https://polymarket.com) prediction markets. Uses machine learning (XGBoost) to detect value bets across NBA, NFL, NHL, and Tennis markets.

## Features

- **Multi-sport coverage** — NBA, NFL, NHL, Tennis with configurable sport filters
- **ML-powered predictions** — XGBoost model for outcome probability estimation
- **Value bet detection** — Compares model predictions against market odds to find edges
- **Automated execution** — Places trades on detected value opportunities autonomously
- **Kelly Criterion sizing** — Fractional Kelly for optimal bet sizing
- **Risk management** — Daily loss limits, per-sport caps, position limits, and cooldowns
- **Live data pipeline** — Real-time odds data with configurable caching
- **Notifications** — Push alerts via ntfy for trades, errors, and status updates

## Architecture

```
main.py                  # Entry point
config.yaml              # Configuration
src/
├── market_scanner.py    # Polymarket sports market discovery
├── data_pipeline.py     # Odds & stats data ingestion
├── predictor.py         # ML prediction engine (XGBoost)
├── value_detector.py    # Edge detection & value calculation
├── executor.py          # Trade execution engine
├── risk_manager.py      # Risk controls & position management
├── notifier.py          # Push notification handler
└── state.py             # State persistence
```

## Prerequisites

- Python 3.10+
- Polymarket account with funded wallet
- Polygon (MATIC) for gas fees
- [Odds API key](https://the-odds-api.com/) (optional, for enhanced data)

## Setup

```bash
git clone https://github.com/PatrickSebastine/polymarket-sports-bot.git
cd polymarket-sports-bot
pip install -r requirements.txt
```

Create a `.env` file:

```env
POLYMARKET_PRIVATE_KEY=your_private_key_here
POLYMARKET_API_KEY=your_api_key_here
POLYMARKET_API_SECRET=your_api_secret_here
POLYMARKET_PASSPHRASE=your_passphrase_here
ODDS_API_KEY=your_odds_api_key_here
```

## Configuration

Edit `config.yaml` to customize:

| Parameter | Default | Description |
|---|---|---|
| `sports.enabled` | `NBA, NFL, NHL, TENNIS` | Active sports markets |
| `sports.min_edge` | `0.05` | Minimum edge to place a bet |
| `sports.min_confidence` | `0.4` | Minimum model confidence |
| `sports.min_liquidity` | `100` | Minimum market liquidity (USD) |
| `risk.daily_loss_limit` | `3.00` | Maximum daily loss (USD) |
| `risk.kelly_fraction` | `0.25` | Kelly Criterion fraction |
| `risk.max_bet_size` | `5.00` | Maximum single bet size (USD) |
| `scan_interval` | `60` | Seconds between scan cycles |

## Usage

```bash
python main.py
```

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## Disclaimer

This software is for educational and research purposes only. Use at your own risk. Trading prediction markets involves financial risk. Past performance does not guarantee future results.
