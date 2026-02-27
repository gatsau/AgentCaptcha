"""REST endpoints: GET /status, GET /verify, GET /sessions/{agent_id}."""
import jwt
from fastapi import APIRouter, HTTPException, Query

from app.database import fetch_agent_sessions, fetch_challenge_history
from app.services.token import decode_token

router = APIRouter()


@router.get("/status")
async def status():
    from app.config import settings
    return {
        "status": "ok",
        "service": "AgentCaptcha DPP",
        "mock_mode": settings.use_mock_challenges,
    }


@router.get("/verify")
async def verify_token(token: str = Query(..., description="JWT token issued after verification")):
    """Decode and inspect a verification JWT. Usage: GET /verify?token=<jwt>"""
    try:
        payload = decode_token(token)
        return {"valid": True, "payload": payload}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


@router.get("/sessions/{agent_id}")
async def get_sessions(agent_id: str):
    """Return all sessions for a given agent_id."""
    sessions = await fetch_agent_sessions(agent_id)
    if not sessions:
        raise HTTPException(status_code=404, detail="No sessions found for agent_id")
    return {"agent_id": agent_id, "sessions": sessions}


@router.get("/sessions/{agent_id}/history/{session_id}")
async def get_challenge_history(agent_id: str, session_id: int):
    """Return per-round challenge history for a session."""
    history = await fetch_challenge_history(session_id)
    if not history:
        raise HTTPException(status_code=404, detail="No challenge history found")
    return {"session_id": session_id, "rounds": history}
