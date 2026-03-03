from kafka import KafkaProducer
import json

producer = KafkaProducer(
    bootstrap_servers="kafka:9092",
    value_serializer=lambda v: json.dumps(v).encode()
)

producer.send("market-data", {"symbol": "BTC", "price": 65000})