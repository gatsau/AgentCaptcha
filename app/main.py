"""FastAPI application with lifespan, WebSocket, and REST routes."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket

from app.api.routes import router
from app.api.websocket import websocket_verify
from app.database import close_db, get_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AgentCaptcha starting — initialising database")
    await get_db()
    yield
    logger.info("AgentCaptcha shutting down — closing database")
    await close_db()


app = FastAPI(
    title="AgentCaptcha",
    description="Decision-Proof Protocol: verify autonomous agents via 4-stage cryptographic + LLM challenge",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.websocket("/ws/verify")
async def ws_verify(websocket: WebSocket):
    await websocket_verify(websocket)
