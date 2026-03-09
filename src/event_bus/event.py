from dataclasses import dataclass
from datetime import datetime
from typing import Any


class Event:
    type: str
    data: Any
    timestamp: datetime = datetime.now()
