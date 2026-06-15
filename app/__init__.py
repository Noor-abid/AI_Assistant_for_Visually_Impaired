"""FastAPI application factory.

Imports for the web framework stay inside ``create_app`` so utility modules
and tests can be imported before server dependencies are installed.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging

from .config import APP_TITLE, STATIC_DIR


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("%s initialized.", APP_TITLE)
    yield
    logging.info("%s shutting down.", APP_TITLE)


def create_app() -> FastAPI:
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles

    from .routes import pages, websocket

    app = FastAPI(
        title=APP_TITLE,
        description="Accessible real-time camera assistance",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(pages.router)
    app.include_router(websocket.router)
    return app


__all__ = ["create_app"]
