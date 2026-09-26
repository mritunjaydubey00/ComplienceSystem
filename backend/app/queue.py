import os

from redis import Redis
from rq import Queue

redis_connection = Redis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    decode_responses=False,
)
ocr_queue = Queue("ocr", connection=redis_connection)