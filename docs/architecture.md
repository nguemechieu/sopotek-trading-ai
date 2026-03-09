# Sopotek Trading AI Architecture

Sopotek Trading AI is an event-driven algorithmic trading platform designed to support multiple financial markets
including cryptocurrency, forex, and stocks.

The system is modular and scalable, allowing independent development of trading components.

-----------------------------------------------------------------------------------

## Core Architecture

The trading pipeline follows this flow:

Market Data  
↓  
Event Bus  
↓  
Strategy Engine  
↓  
Risk Engine  
↓  
Execution Engine  
↓  
Portfolio Manager  
↓  
Storage / Analytics

---------------------------------------------------------------------------------

## Event Driven System

The platform uses an event bus to coordinate communication between components.

Components publish and subscribe to events rather than calling each other directly.

Benefits:

- modular design
- asynchronous execution
- high scalability

-----------------------------------------------------------------------------------

## Major Modules

### Core

Controls system orchestration and scheduling.
core/
orchestrator.py
trading_engine.py
scheduler.py
system_state.py


--------------------------------------------------------------------------------

### Broker

Provides unified access to external exchanges.

broker/
ccxt_broker.py
oanda_broker.py
alpaca_broker.py


----------------------------------------------------------------------------------

### Market Data

Handles streaming and storage of real-time market data.

market_data/
candle_buffer.py
orderbook_buffer.py
websocket/


---------------------------------------------------

### Strategy

Contains trading strategies.

strategy/
momentum_strategy.py
mean_reversion.py
arbitrage_strategy.py


-----------------------------------------------------------------------------------

### Risk

Ensures trades obey portfolio and risk constraints.

risk/
institutional_risk.py
exposure_manager.py
drawdown_guard.py


----------------------------------------------------

### Execution

Handles order placement and smart execution logic.

execution/
execution_manager.py
order_router.py


---------------------------------------------------

### Portfolio

Tracks open positions and calculates profit/loss.

portfolio/
portfolio_manager.py
pnl_engine.py


------------------------------------------------------

### Quant

Contains analytics, feature engineering, and machine learning models.

quant/
features/
ml/
analytics/


----------------------------------------------------

### Backtesting

Allows simulation of strategies on historical data.

backtesting/
backtest_engine.py
simulator.py


-----------------------------------------------------

## Data Pipeline

Market data flows through multiple stages:

Exchange → Raw Data → Processed Data → Feature Engineering → ML Models

data/raw
data/processed
data/features


--------------------------------------------------------------------------------

## Deployment

The platform can run in:

- paper trading mode
- live trading mode
- backtesting mode