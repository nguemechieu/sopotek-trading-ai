from celery import Celery
import os

celery_app = Celery(
    "sopotek",
    broker=os.getenv("REDIS_URL"),
    backend=os.getenv("REDIS_URL")
)

celery_app.conf.task_routes = {
    "sopotek_trading.tasks.*": {"queue": "trading"}
}