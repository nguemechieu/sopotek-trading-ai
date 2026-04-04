from __future__ import annotations

import logging
import time
from typing import Any, Callable


class RetrainingScheduler:
    """Simple periodic retraining loop for the trade-outcome model."""

    def __init__(
        self,
        retrain_callback: Callable[[], Any],
        *,
        interval_hours: float = 24.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        logger: logging.Logger | None = None,
    ) -> None:
        self.retrain_callback = retrain_callback
        self.interval_hours = max(0.01, float(interval_hours))
        self.sleep_fn = sleep_fn
        self.logger = logger or logging.getLogger("sopotek.ml.retraining")

    def run_once(self) -> Any:
        self.logger.info("Retraining ML model")
        return self.retrain_callback()

    def run_forever(self) -> None:
        while True:
            self.run_once()
            self.sleep_fn(self.interval_hours * 3600.0)


def retrain_loop(
    retrain_callback: Callable[[], Any],
    *,
    interval_hours: float = 24.0,
    sleep_fn: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> None:
    RetrainingScheduler(
        retrain_callback,
        interval_hours=interval_hours,
        sleep_fn=sleep_fn,
        logger=logger,
    ).run_forever()
