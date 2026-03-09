import pandas as pd

from src.backtesting.simulator import Simulator
from src.strategy.momentum_strategy import MomentumStrategy

from backtesting.backtest_engine import BacktestEngine
from backtesting.report_generator import Report, ReportGenerator
def main():

    df = pd.read_csv("data/processed/btc_1h.csv")

    strategy = MomentumStrategy(None)

    simulator = Simulator(initial_balance=10000)

    engine = BacktestEngine(strategy, simulator)

    results = engine.run(df)

    report = ReportGenerator().generate(results)

    print("\nBacktest Results")
    print(report)


if __name__ == "__main__":
    main()