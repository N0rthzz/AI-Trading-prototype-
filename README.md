# North Trading System

**An LLM-assisted trading prototype built with Python, Next.js, and OpenTyphoon.**

North Trading System combines market news, technical indicators, and LLM analysis to generate **BUY, SELL, and HOLD** signals. A Next.js dashboard provides watchlist management and displays analysis history, while a Python engine handles data collection, AI analysis, broker execution, and Telegram notifications.

**Status:** In development. Broker execution and strategy performance have not been comprehensively validated.

## Overview

The project explores how financial data and language models can be integrated into a trading workflow.

For each asset in the watchlist, the system:

1. Collects market news and historical price data.
2. Calculates technical indicators.
3. Translates news headlines into Thai.
4. Sends news and technical summaries to OpenTyphoon.
5. Receives factor scores, a trading signal, and Thai-language reasoning.
6. Processes the signal according to the configured trading mode.
7. Saves the analysis to SQLite for dashboard review.

## Features

### Market Data and Technical Analysis

- Historical price data through `yfinance`.
- Stock news from Yahoo Finance.
- Google News RSS as an alternative news source.
- Technical indicators and market context:
  - RSI (14)
  - EMA (20 and 50)
  - MACD and signal line
  - 20-day support and resistance
  - Volume compared with its 20-day average
  - P/E ratio when available
- Ticker conversion for selected stock, cryptocurrency, forex, and gold inputs.

### LLM Analysis

- OpenTyphoon integration through the OpenAI-compatible SDK.
- Thai translation of financial news headlines.
- Analysis across four factors:
  - **Macro:** macroeconomic context
  - **Geo:** geopolitical context
  - **Tech:** technical market signals
  - **Asset:** asset-specific context
- JSON output containing factor scores, a master score, an action, and reasoning.

### Web Dashboard

- Broker selection and configuration.
- SIGNAL and LIVE mode selection.
- Watchlist creation and removal.
- Display of up to 15 recent analysis records.
- Factor scores, trading signals, Thai reasoning, news, and technical summaries.

### Execution and Automation

- Broker integration code for Alpaca, Binance, and MetaTrader 5.
- Position checks before selected order operations.
- Telegram notifications for BUY and SELL signals.
- Daily scheduling through the Python `schedule` package.

## Architecture

The Python engine and Next.js dashboard share a local SQLite database.

| Component | Responsibility |
| --- | --- |
| Next.js dashboard | Manage watchlist and settings; display analysis history |
| Python engine | Collect data, calculate indicators, call the LLM, and process signals |
| SQLite | Store watchlist, broker settings, and analysis records |
| OpenTyphoon | Translate headlines and generate analysis |
| Broker integrations | Submit orders when execution is enabled |
| Telegram | Deliver signal notifications |

The current implementation uses direct database access rather than a REST API between the dashboard and Python engine.

## Technology Stack

| Layer | Technologies |
| --- | --- |
| Analysis engine | Python |
| Frontend | Next.js, React, TypeScript |
| Styling | Tailwind CSS |
| Database | SQLite |
| Frontend database access | `better-sqlite3` |
| Market data | `yfinance`, Yahoo Finance, Google News RSS |
| Technical analysis | Pandas, `pandas_ta` |
| LLM client | OpenAI SDK connected to OpenTyphoon |
| Stock execution | Alpaca |
| Cryptocurrency execution | CCXT / Binance |
| Forex execution | MetaTrader 5 |
| Notifications | Telegram Bot API |
| Scheduling | `schedule` |

## AI Decision Process

The engine currently uses:

```text
typhoon-v2.5-30b-a3b-instruct
```

A single analysis request asks the model to evaluate all four factors and return:

- `action`
- `z_score`
- `scores`
- `reasoning`

The prompt defines the following decision thresholds:

| Master score | Requested action |
| --- | --- |
| Greater than 0.60 | BUY |
| Less than -0.60 | SELL |
| Otherwise | HOLD |

### Implementation Notes

- The field named `z_score` is an **LLM-generated master score**, not a statistically calculated Z-score.
- The current engine reads the action returned by the model; it does not independently recompute the action from the score.
- Factor weights are declared in the code but are not currently used to calculate the master score.
- Despite the class name `QuantMultiAgentTrader`, the implemented analysis uses one LLM request rather than separate agents for each factor.
- The OpenAI SDK acts as a client for OpenTyphoon. The current analysis code does not call an OpenAI model.

## Trading Modes

### SIGNAL

The engine generates and stores analysis without submitting broker orders. Telegram notifications may still be sent for BUY and SELL signals.

### LIVE

The mode enables the broker execution branch. The actual execution environment depends on the broker configuration in the code:

| Broker | Current behavior |
| --- | --- |
| Alpaca | Uses paper trading through `paper=True` |
| Binance | Uses sandbox mode |
| MetaTrader 5 | Sends requests to the logged-in terminal account |

The LIVE label therefore does not mean that all broker integrations use real-money trading.

### Current Order Behavior

- **Alpaca:** Checks for an existing position. A BUY uses approximately 5% of buying power, with a minimum requested notional of $1. A SELL closes the existing position.
- **Binance:** Uses spot sandbox orders. A BUY targets approximately 20 quote-currency units; a SELL uses the available base-asset balance.
- **MetaTrader 5:** Includes a fixed-volume order request of 0.01 lots. Position-closing behavior still requires correction and validation.

## Database

The implementation defines the following tables:

| Table | Purpose |
| --- | --- |
| `SystemSettings` | Broker credentials and trading mode |
| `Watchlist` | Assets queued for analysis |
| `TradeHistory` | Analysis records written by the current engine |
| `TradeDecision` | Earlier analysis schema, still referenced by one dashboard implementation |

The current Python engine saves results to **`TradeHistory`**. The dashboard must read this table to display new analysis results.

Both components must resolve to the same `trade_database.db` file. The frontend currently looks for the database one directory above its working directory, while the Python engine uses relative database paths.

## Local Setup

### 1. Get the Backend Source

```bash
git clone https://github.com/N0rthzz/AI-Trading-prototype-.git
cd AI-Trading-prototype-
```

The reviewed GitHub repository contains the Python engine. The Next.js frontend is maintained separately in the supplied project files.

### 2. Install Python Dependencies

Create and activate a Python virtual environment, then run:

```bash
pip install -r requirements.txt
```

The dependency list includes MetaTrader 5. Installation and execution depend on platform compatibility and the availability of a configured MT5 terminal.

### 3. Configure Environment Variables

Create a local `.env` file using `.env.example` as a reference.

The engine reads:

```dotenv
TYPHOON_API_KEY=your_typhoon_api_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
```

Typhoon credentials are required for AI analysis. Telegram credentials are optional; alerts are skipped when they are missing.

Broker credentials are entered through the setup page and stored in `SystemSettings`.

### 4. Initialize the Database

From the backend directory:

```bash
cd AI-trader-system
python trader_bot.py
```

The engine initializes its base database tables. If the watchlist is empty, it exits without analyzing assets.

Before continuing, ensure that the frontend's database path points to this same database file.

### 5. Start the Frontend

In the Next.js frontend directory containing `package.json`:

```bash
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

Use the setup interface to select a mode, then add assets to the watchlist.

The original App Router directory structure must be preserved. Uploaded filenames such as `page(1).tsx` and `page(2).tsx` do not establish their original route locations.

### 6. Run an Analysis Cycle

From the backend directory:

```bash
python trader_bot.py
```

The engine processes the watchlist and stores each analysis in SQLite. Reload the dashboard to review the latest records.

### 7. Enable Scheduled Runs

From the same backend directory:

```bash
python auto_runner.py
```

The scheduler runs the engine daily at **08:00 according to the host machine's local time**. The process must remain running.

## Current Limitations

- Broker setup currently checks only that credential fields are populated; it does not verify credentials with the broker.
- Broker credentials are stored as plaintext in SQLite.
- The backend includes debug statements that print the Typhoon API key. These should be removed before running with credentials.
- Dashboard implementations reference different history tables.
- Dashboard status labels do not verify whether the Python engine is running or a broker connection is healthy.
- Analysis results require a page reload; the supplied dashboard code does not implement polling or streaming updates.
- LLM output is parsed as JSON without complete schema, range, or action validation.
- News and price retrieval depend on external services.
- Symbol formats are not fully normalized across market-data providers and brokers.
- No backtesting, verified profitability metrics, or comprehensive execution tests are included in the reviewed source.
- Analysis records represent generated decisions and do not establish that an order was successfully filled.

## Development Roadmap

- Unify database paths and history schemas.
- Validate broker credentials through actual broker APIs.
- Validate LLM output and enforce decision thresholds in Python.
- Replace the `z_score` label with a clearer master-score name.
- Remove credential debug output and improve credential storage.
- Normalize symbols for each supported broker.
- Correct and test MetaTrader 5 position-closing logic.
- Add dashboard refresh and engine health checks.
- Add backtesting, transaction-cost modeling, and performance reporting.
- Record order status and fills separately from analysis decisions.

## Author

**Nontawat Samlee**

GitHub: [N0rthzz](https://github.com/N0rthzz)
