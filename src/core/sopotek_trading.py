import asyncio
import logging
from datetime import datetime, timezone

from manager.portfolio_manager import PortfolioManager
from execution.execution_manager import ExecutionManager
from strategy.strategy_registry import StrategyRegistry
from engines.risk_engine import RiskEngine
from execution.order_router import OrderRouter
from event_bus.event_bus import EventBus
from core.multi_symbol_orchestrator import MultiSymbolOrchestrator
from quant.data_hub import QuantDataHub
from quant.portfolio_allocator import PortfolioAllocator
from quant.portfolio_risk_engine import PortfolioRiskEngine
from quant.signal_engine import SignalEngine
from risk.trader_behavior_guard import TraderBehaviorGuard


class SopotekTrading:

    def __init__(self, controller=None):

        self.controller = controller
        self.logger = logging.getLogger(__name__)

        # =========================
        # BROKER
        # =========================

        self.broker = getattr(controller, "broker", None)

        if self.broker is None:
            raise RuntimeError("Broker not initialized")

        required_methods = ("fetch_ohlcv", "fetch_balance", "create_order")
        missing = [name for name in required_methods if not hasattr(self.broker, name)]
        if missing:
            raise RuntimeError(
                "Controller broker is missing required capabilities: " + ", ".join(missing)
            )

        self.symbols = getattr(controller, "symbols", ["BTC/USDT", "ETH/USDT"])

        # =========================
        # CORE COMPONENTS
        # =========================

        self.strategy = StrategyRegistry()
        self._apply_strategy_preferences()
        self.data_hub = QuantDataHub(
            controller=self.controller,
            market_data_repository=getattr(controller, "market_data_repository", None),
            broker=self.broker,
        )
        self.signal_engine = SignalEngine(self.strategy)

        self.event_bus = EventBus()

        self.portfolio = PortfolioManager(event_bus=self.event_bus)

        self.router = OrderRouter(broker=self.broker)
        self.behavior_guard = TraderBehaviorGuard(
            max_orders_per_hour=24,
            max_orders_per_day=120,
            max_consecutive_losses=4,
            cooldown_after_loss_seconds=900,
            same_symbol_reentry_cooldown_seconds=300,
            max_size_jump_ratio=3.0,
            daily_drawdown_limit_pct=0.06,
        )
        if self.controller is not None:
            self.controller.behavior_guard = self.behavior_guard

        self.execution_manager = ExecutionManager(
            broker=self.broker,
            event_bus=self.event_bus,
            router=self.router,
            trade_repository=getattr(controller, "trade_repository", None),
            trade_notifier=getattr(controller, "handle_trade_execution", None),
            behavior_guard=self.behavior_guard,
        )

        self.risk_engine = None
        self.portfolio_allocator = None
        self.portfolio_risk_engine = None
        self.orchestrator = None

        # =========================
        # SYSTEM SETTINGS
        # =========================

        self.time_frame = getattr(controller, "time_frame", "1h")
        self.limit = getattr(controller, "limit", 50000)
        self.running = False
        self._pipeline_status = {}

        self.logger.info("Sopotek Trading System initialized")

    def _apply_strategy_preferences(self):
        strategy_name = getattr(self.controller, "strategy_name", None)
        strategy_params = getattr(self.controller, "strategy_params", None)
        self.strategy.configure(strategy_name=strategy_name, params=strategy_params)

    def _resolve_execution_strategy(self, symbol, side, amount, price, signal):
        requested = str(signal.get("execution_strategy") or "").strip().lower()
        if requested:
            return requested

        order_type = str(signal.get("type") or "market").strip().lower()
        portfolio_equity = None
        try:
            portfolio_equity = self.portfolio.equity()
        except Exception:
            portfolio_equity = None
        equity = float(portfolio_equity or getattr(self.risk_engine, "account_equity", 0.0) or 0.0)
        notional = abs(float(amount or 0.0) * float(price or 0.0))
        if equity <= 0 or notional <= 0:
            return order_type

        notional_pct = notional / equity
        if order_type in {"limit", "stop_limit"} and notional_pct >= 0.08:
            return "iceberg"
        if order_type == "market" and notional_pct >= 0.05:
            return "twap"
        return order_type

    def _record_pipeline_status(self, symbol, stage, status, detail=None, signal=None):
        normalized_symbol = str(symbol or "").strip().upper()
        if not normalized_symbol:
            return

        snapshot = {
            "symbol": normalized_symbol,
            "stage": str(stage or "").strip() or "unknown",
            "status": str(status or "").strip() or "unknown",
            "detail": str(detail or "").strip(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if isinstance(signal, dict):
            snapshot["strategy_name"] = signal.get("strategy_name") or getattr(self.controller, "strategy_name", None)
            snapshot["side"] = signal.get("side")
            snapshot["confidence"] = signal.get("confidence")
        self._pipeline_status[normalized_symbol] = snapshot

    def pipeline_status_snapshot(self):
        return {
            symbol: dict(payload)
            for symbol, payload in (self._pipeline_status or {}).items()
        }

    async def process_symbol(self, symbol, timeframe=None, limit=None, publish_debug=True):
        normalized_symbol = str(symbol or "").strip().upper()
        if not normalized_symbol:
            raise ValueError("Symbol is required")

        target_timeframe = str(timeframe or self.time_frame or "1h").strip() or "1h"
        target_limit = max(1, int(limit or self.limit or 300))

        dataset = await self.data_hub.get_symbol_dataset(
            symbol=normalized_symbol,
            timeframe=target_timeframe,
            limit=target_limit,
        )
        candles = dataset.to_candles()
        if not candles:
            self._record_pipeline_status(normalized_symbol, "data_hub", "empty", "No candles returned for symbol")
            return None

        signal = self.signal_engine.generate_signal(
            candles=candles,
            dataset=dataset,
            strategy_name=getattr(self.controller, "strategy_name", None),
            symbol=normalized_symbol,
        )

        features = getattr(dataset, "frame", None)
        display_signal = signal or {
            "symbol": normalized_symbol,
            "side": "hold",
            "amount": 0.0,
            "confidence": 0.0,
            "reason": "No entry signal on the latest scan.",
            "strategy_name": getattr(self.controller, "strategy_name", None),
        }

        if publish_debug and self.controller and hasattr(self.controller, "publish_ai_signal"):
            self.controller.publish_ai_signal(normalized_symbol, display_signal, candles=candles)
        if publish_debug and self.controller and hasattr(self.controller, "publish_strategy_debug"):
            self.controller.publish_strategy_debug(
                normalized_symbol,
                display_signal,
                candles=candles,
                features=features,
            )

        if signal:
            self._record_pipeline_status(normalized_symbol, "signal_engine", "signal", signal.get("reason"), signal=signal)
        else:
            self._record_pipeline_status(normalized_symbol, "signal_engine", "hold", display_signal.get("reason"), signal=display_signal)
            return None

        if self.controller and hasattr(self.controller, "apply_news_bias_to_signal"):
            signal = await self.controller.apply_news_bias_to_signal(normalized_symbol, signal)
            if not signal:
                self._record_pipeline_status(
                    normalized_symbol,
                    "news_bias",
                    "blocked",
                    "Signal was neutralized by news bias controls.",
                    signal=display_signal,
                )
                return None

        result = await self.process_signal(normalized_symbol, signal, dataset=dataset)
        if result is None:
            latest = self._pipeline_status.get(normalized_symbol, {})
            if latest.get("status") in {"rejected", "blocked"}:
                return None
            self._record_pipeline_status(
                normalized_symbol,
                "execution_manager",
                "skipped",
                "Signal did not result in an executable order.",
                signal=signal,
            )
            return None

        execution_status = str(result.get("status") or "submitted").strip().lower() if isinstance(result, dict) else "submitted"
        self._record_pipeline_status(
            normalized_symbol,
            "execution_manager",
            execution_status,
            result.get("reason") if isinstance(result, dict) else "",
            signal=signal,
        )
        return result

    # ==========================================
    # START SYSTEM
    # ==========================================

    async def start(self):
        if self.running:
            self.logger.info("Trading system already running")
            return

        if self.broker is None:
            raise RuntimeError("Broker not initialized")



        balance = getattr(self.controller, "balances", {}) or {}
        equity = float(getattr(self.controller, "initial_capital", 10000) or 10000)
        if isinstance(balance, dict):
            total = balance.get("total")
            if isinstance(total, dict):
                for currency in ("USDT", "USD", "USDC", "BUSD"):
                    value = total.get(currency)
                    if value is None:
                        continue
                    try:
                        equity = float(value)
                        break
                    except Exception:
                        continue



        self.risk_engine = RiskEngine(
            account_equity=equity,
            max_portfolio_risk=getattr(self.controller, "max_portfolio_risk", 100),
            max_risk_per_trade=getattr(self.controller, "max_risk_per_trade", 50),
            max_position_size_pct=getattr(self.controller, "max_position_size_pct", 25),
            max_gross_exposure_pct=getattr(self.controller, "max_gross_exposure_pct", 30),
        )
        active_strategy = getattr(self.controller, "strategy_name", None) or "Trend Following"
        self.portfolio_allocator = PortfolioAllocator(
            account_equity=equity,
            strategy_weights={str(active_strategy): 1.0},
            allocation_model="equal_weight",
            max_strategy_allocation_pct=1.0,
            rebalance_threshold_pct=0.15,
            volatility_target_pct=0.20,
        )
        self.portfolio_risk_engine = PortfolioRiskEngine(
            account_equity=equity,
            max_portfolio_risk=getattr(self.controller, "max_portfolio_risk", 0.10),
            max_risk_per_trade=getattr(self.controller, "max_risk_per_trade", 0.02),
            max_position_size_pct=getattr(self.controller, "max_position_size_pct", 0.10),
            max_gross_exposure_pct=getattr(self.controller, "max_gross_exposure_pct", 2.0),
            max_symbol_exposure_pct=min(
                0.30,
                max(0.05, float(getattr(self.controller, "max_position_size_pct", 0.10) or 0.10) * 1.5),
            ),
        )
        if self.controller is not None:
            self.controller.portfolio_allocator = self.portfolio_allocator
            self.controller.institutional_risk_engine = self.portfolio_risk_engine
        if self.behavior_guard is not None:
            self.behavior_guard.record_equity(equity)

        self.orchestrator = MultiSymbolOrchestrator(controller=self.controller,
            broker=self.broker,
            strategy=self.strategy,
            execution_manager=self.execution_manager,
            risk_engine=self.risk_engine,
            signal_processor=self.process_symbol,
        )


        self.running = True
        self.logger.info(f"Loaded {len(self.symbols)} symbols")
        await self.execution_manager.start()
        await self.orchestrator.start(symbols=self.symbols)

    # ==========================================
    # MAIN TRADING LOOP
    # ==========================================

    async def run(self):

        self.logger.info("Trading loop started")

        while self.running:

            try:
                active_symbols = self.symbols[:100]
                if self.controller and hasattr(self.controller, "get_active_autotrade_symbols"):
                    try:
                        resolved = self.controller.get_active_autotrade_symbols()
                    except Exception:
                        resolved = []
                    if resolved:
                        active_symbols = resolved[:100]

                for symbol in active_symbols:
                    await self.process_symbol(
                        symbol,
                        timeframe=self.time_frame,
                        limit=self.limit,
                        publish_debug=True,
                    )

                await asyncio.sleep(5)

            except Exception:
                self.logger.exception("Trading loop error")

    # ==========================================
    # PROCESS SIGNAL
    # ==========================================

    async def process_signal(self, symbol, signal, dataset=None):

        side = signal["side"]
        price = signal.get("price")
        amount = signal["amount"]
        strategy_name = signal.get("strategy_name") or getattr(self.controller, "strategy_name", "Bot")
        if (price is None or float(price or 0) <= 0) and dataset is not None and not getattr(dataset, "empty", True):
            try:
                price = float(dataset.frame.iloc[-1]["close"])
            except Exception:
                price = None
        if price is None or float(price or 0) <= 0:
            self.logger.warning("Trade rejected because no executable reference price was available for %s", symbol)
            return

        basic_reason = "Approved"
        if hasattr(self.risk_engine, "adjust_trade"):
            allowed, adjusted_amount, basic_reason = self.risk_engine.adjust_trade(float(price), float(amount))
        else:
            allowed, basic_reason = self.risk_engine.validate_trade(float(price), float(amount))
            adjusted_amount = float(amount)

        if not allowed:
            self.logger.warning("Trade rejected by risk engine: %s", basic_reason)
            self._record_pipeline_status(symbol, "risk_engine", "rejected", basic_reason, signal=signal)
            return
        if adjusted_amount + 1e-12 < float(amount):
            self.logger.info(
                "Risk engine reduced %s order size from %.8f to %.8f: %s",
                symbol,
                float(amount),
                adjusted_amount,
                basic_reason,
            )
        amount = adjusted_amount
        self._record_pipeline_status(symbol, "risk_engine", "approved", basic_reason, signal=signal)

        if self.portfolio_allocator is not None:
            try:
                portfolio_equity = self.portfolio.equity()
            except Exception:
                portfolio_equity = None
            if portfolio_equity:
                self.portfolio_allocator.sync_equity(portfolio_equity)
            allocation = await self.portfolio_allocator.allocate_trade(
                symbol=symbol,
                strategy_name=strategy_name,
                side=side,
                amount=amount,
                price=price,
                portfolio=getattr(self.portfolio, "portfolio", None),
                market_prices=getattr(self.portfolio, "market_prices", {}),
                dataset=dataset,
                confidence=signal.get("confidence"),
                active_strategies=[strategy_name],
            )
            if self.controller is not None:
                self.controller.quant_allocation_snapshot = dict(allocation.metrics or {})
            if not allocation.approved:
                self.logger.warning("Trade rejected by portfolio allocator: %s", allocation.reason)
                self._record_pipeline_status(symbol, "portfolio_allocator", "rejected", allocation.reason, signal=signal)
                return
            amount = allocation.adjusted_amount
            self._record_pipeline_status(symbol, "portfolio_allocator", "approved", allocation.reason, signal=signal)

        if self.portfolio_risk_engine is not None:
            try:
                portfolio_equity = self.portfolio.equity()
            except Exception:
                portfolio_equity = None
            if portfolio_equity:
                self.portfolio_risk_engine.sync_equity(portfolio_equity)
            approval = await self.portfolio_risk_engine.approve_trade(
                symbol=symbol,
                side=side,
                amount=amount,
                price=price,
                portfolio=getattr(self.portfolio, "portfolio", None),
                market_prices=getattr(self.portfolio, "market_prices", {}),
                data_hub=self.data_hub,
                dataset=dataset,
                timeframe=self.time_frame,
                strategy_name=signal.get("strategy_name") or getattr(self.controller, "strategy_name", None),
            )
            if self.controller is not None:
                self.controller.quant_risk_snapshot = dict(approval.metrics or {})
            if not approval.approved:
                self.logger.warning("Trade rejected by institutional risk engine: %s", approval.reason)
                self._record_pipeline_status(symbol, "portfolio_risk_engine", "rejected", approval.reason, signal=signal)
                return
            amount = approval.adjusted_amount
            self._record_pipeline_status(symbol, "portfolio_risk_engine", "approved", approval.reason, signal=signal)

        if self.portfolio_allocator is not None:
            self.portfolio_allocator.register_strategy_symbol(symbol, strategy_name)

        execution_strategy = self._resolve_execution_strategy(symbol, side, amount, price, signal)

        order = await self.execution_manager.execute(
            symbol=symbol,
            side=side,
            amount=amount,
            price=price,
            source="bot",
            strategy_name=strategy_name,
            reason=signal.get("reason"),
            confidence=signal.get("confidence"),
            expected_price=signal.get("price"),
            pnl=signal.get("pnl"),
            execution_strategy=execution_strategy,
            type=signal.get("type", "market"),
            params=signal.get("params"),
        )

        return order

    # ==========================================
    # STOP SYSTEM
    # ==========================================

    async def stop(self):

        self.logger.info("Stopping trading system")

        self.running = False

        orchestrator = getattr(self, "orchestrator", None)
        if orchestrator is not None:
            for worker in list(getattr(orchestrator, "workers", []) or []):
                try:
                    worker.running = False
                except Exception:
                    pass
            shutdown = getattr(orchestrator, "shutdown", None)
            if callable(shutdown):
                try:
                    await shutdown()
                except Exception:
                    self.logger.exception("Orchestrator shutdown failed")

        execution_manager = getattr(self, "execution_manager", None)
        if execution_manager is not None:
            try:
                await execution_manager.stop()
            except Exception:
                self.logger.exception("Execution manager stop failed")
