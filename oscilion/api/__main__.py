"""Lanza la API: `python -m oscilion.api`."""
import uvicorn

from config import config
from oscilion.logging_setup import setup_logging


def main() -> None:
    setup_logging()
    uvicorn.run(
        "oscilion.api.app:app",
        host=config.api_host,
        port=config.api_port,
        log_level=config.log_level.lower(),
    )


if __name__ == "__main__":
    main()
