from kafka import KafkaConsumer
import json

from sopotek_trading.backend.kafka.real_time_price_feed import process_market_data

consumer = KafkaConsumer(
    "market-data",
    bootstrap_servers="kafka:9092",
    value_deserializer=lambda m: json.loads(m.decode())
)

for message in consumer:
    process_market_data(message.value)