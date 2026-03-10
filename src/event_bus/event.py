from datetime import datetime
from typing import Any, Optional


class Event:
    def __init__(self, event_type: Optional[str] = None, data: Any = None, timestamp: Optional[datetime] = None, **kwargs):
        # Support both Event(type=..., data=...) and Event(event_type, data)
        if event_type is None:
            event_type = kwargs.get("type")
        if data is None and "data" in kwargs:
            data = kwargs.get("data")

        self.type = event_type
        self.data = data
        self.timestamp = timestamp or kwargs.get("timestamp") or datetime.now()
