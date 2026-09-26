from rq import Worker

from app.queue import ocr_queue, redis_connection


def main() -> None:
    Worker([ocr_queue], connection=redis_connection).work()


if __name__ == "__main__":
    main()