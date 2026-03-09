docs/api.md

# Sopotek Trading AI – Internal API Documentation

This document describes the internal APIs used by Sopotek Trading AI.

The system is modular and event-driven. Each module communicates through defined interfaces to ensure scalability and
maintainability.

--------------------------------------------------------------------------------------

# Core Components

The main components of the system are:

Market Data  
Strategy Engine  
Risk Engine  
Execution Engine  
Portfolio Manager  
Broker Interface

These components communicate using the Event Bus.

---

# Event Bus API

The event bus allows components to publish and subscribe to events.

## Publish Event

event_bus.publish(event)

## Subscribe to Event

event_bus.subscribe(event_type, handler)

## Event Structure

{
"type": "MARKET_DATA",
"symbol": "BTC/USDT",
"data": {...}
}


---

# Broker API

All broker implementations must inherit from `BaseBroker`.

## Required Methods

### connect()

Establish connection to exchange.

await broker.connect()

### close()

Close exchange connection.

await broker.close()

### fetch_ticker(symbol)

Returns latest ticker information.

Example:

ticker = await broker.fetch_ticker("BTC/USDT")

Response example:

{
"symbol": "BTC/USDT",
"price": 68120.5
}

### fetch_order_book(symbol)

Returns order book data.

orderbook = await broker.fetch_order_book("BTC/USDT")

### create_order()

Submit trade order.

await broker.create_order(
symbol="BTC/USDT",
side="BUY",
amount=0.01,
type="market"
)

### cancel_order()

Cancel existing order.

await broker.cancel_order(order_id)

### fetch_balance()

Returns account balance.

Example:

balance = await broker.fetch_balance()

Response example:

{
"equity": 10000,
"free": 9500,
"used": 500
}


---

# Strategy API

All strategies inherit from `BaseStrategy`.

## on_bar(candle)

Receives new market data and returns a trading signal.

signal = strategy.on_bar(candle)

Example candle:

{
"timestamp": "2026-03-07 10:00",
"open": 68000,
"high": 68200,
"low": 67900,
"close": 68100,
"volume": 120
}

Example signal:

{
"symbol": "BTC/USDT",
"side": "BUY",
"amount": 0.01
}


---

# Risk Engine API

Ensures trades comply with risk rules.

## validate_trade()

approved, message = risk_engine.validate_trade(price, quantity)

## position_size()

Calculates optimal position size.

size = risk_engine.position_size(entry_price, stop_price)


---

# Execution Manager API

Handles order routing to broker.

## execute_order()

await execution_manager.execute_order(order)

Order example:

{
"symbol": "BTC/USDT",
"side": "BUY",
"amount": 0.01
}


---

# Portfolio Manager API

Tracks positions and PnL.

## update_position()

portfolio.update_position(symbol, quantity, price)

## get_positions()

positions = portfolio.get_positions()

Example response:

[
{
"symbol": "BTC/USDT",
"quantity": 0.01,
"entry_price": 68000
}
]


---

# Market Data API

Handles real-time data streaming.

## subscribe()

Subscribe to market data.

market_data.subscribe("BTC/USDT")

## on_tick()

Processes incoming tick data.

market_data.on_tick(data)

Example tick:

{
"symbol": "BTC/USDT",
"price": 68120,
"timestamp": 1710000000
}


---

# Backtesting API

Simulates trading strategies on historical data.

## run()

results = backtest_engine.run(dataframe)

Example output:

{
"total_profit": 4200,
"win_rate": 0.56,
"max_drawdown": 800
}


---

# Storage API

Handles persistence of trades and market data.

## save_trade()

trade_repository.save_trade(symbol, side, quantity, price)

## get_trades()

trades = trade_repository.get_trades()


---

# Configuration API

Configuration values are loaded from the `config/` folder.

Example:

from config.settings import settings

settings.exchanges
settings.strategies
settings.risk


---

# Testing API

Run tests using:

pytest tests/


---

# Supported Markets

Crypto → CCXT  
Forex → OANDA  
Stocks → Alpaca

---

# Future API Extensions

Planned additions include:

- portfolio optimization API
- reinforcement learning strategies
- distributed strategy execution
- GPU model inference

---