# Trading Strategies

This document describes the trading strategies implemented in Sopotek Trading AI.

----------------------------------------------------------------------------------------------

## Momentum Strategy

Momentum strategies assume that assets trending in a direction will continue moving in that direction.

### Logic

Short moving average crosses above long moving average → BUY

Short moving average crosses below long moving average → SELL

### Indicators

- Moving Average (MA)
- Exponential Moving Average (EMA)

-------------------------------------------------------------------------------------------------------

## Mean Reversion Strategy

Mean reversion assumes prices return to their average over time.

### Logic

Price significantly below average → BUY

Price significantly above average → SELL

### Indicators

- Bollinger Bands
- Z-score
- Moving Average

------------------------------------------------------------------------------------

## Arbitrage Strategy

Arbitrage strategies exploit price differences between exchanges.

Example:

BTC price on Exchange A = 68000  
BTC price on Exchange B = 68500

Trade:

Buy Exchange A  
Sell Exchange B

Profit = spread − fees

----------------------------------------------------------------------------------------------

## Machine Learning Strategies

Machine learning models predict market behavior using historical data.

Examples:

- Random Forest
- XGBoost
- Hidden Markov Models

These models use features generated in the `data/features` pipeline.

-----------------------------------------------------------------------------------------

## Risk Controls

Every strategy must pass through the risk engine before execution.

Risk checks include:

- max position size
- portfolio exposure
- drawdown protection