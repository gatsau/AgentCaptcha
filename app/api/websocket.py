"""WebSocket handler: runs the verifier over a persistent connection."""
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from app.protocol.verifier import verify

logger = logging.getLogger(__name__)


async def websocket_verify(websocket: WebSocket):
    await websocket.accept()

    agent_id = websocket.query_params.get("agent_id")

    async def ws_send(data: dict):
        await websocket.send_text(json.dumps(data))

    async def ws_recv() -> dict:
        raw = await websocket.receive_text()
        return json.loads(raw)

    try:
        result = await verify(ws_send, ws_recv, agent_id=agent_id)
        logger.info(
            "Verification %s for agent=%s stages=%s",
            result.verdict,
            agent_id,
            result.stages_passed,
        )
    except WebSocketDisconnect:
        logger.info("Client disconnected mid-verification agent=%s", agent_id)
    except Exception as exc:
        logger.exception("Unhandled error during verification: %s", exc)
        try:
            await websocket.send_text(
                json.dumps({"type": "error", "message": str(exc)})
            )
        except Exception:
            pass
