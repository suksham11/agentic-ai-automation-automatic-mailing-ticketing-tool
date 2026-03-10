from redis import Redis

from app.core.config import get_settings


def run_worker() -> None:
    """Minimal worker placeholder for future background ticket actions."""
    settings = get_settings()
    client = Redis.from_url(settings.redis_url)
    pong = client.ping()
    print(f"Redis connected: {pong}")


if __name__ == "__main__":
    run_worker()
