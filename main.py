"""Application entry point."""

import logging
import sys

from app.config import HOST, LOG_LEVEL, PORT

try:
    import uvicorn
except ModuleNotFoundError:  # pragma: no cover - exercised by integration use
    uvicorn = None


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if uvicorn is None:
        logging.warning("Uvicorn is not installed; starting the no-network local runner.")
        from dev_server import main as dev_main

        dev_main()
        return

    try:
        uvicorn.run(
            "app:create_app",
            host=HOST,
            port=PORT,
            reload=True,
            factory=True,
            log_level=LOG_LEVEL.lower(),
            ws_ping_interval=25,
            ws_ping_timeout=60,
        )
    except KeyboardInterrupt:
        logging.info("Application stopped.")
    except Exception as exc:
        logging.critical("Application failed to start: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
