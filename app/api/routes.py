"""REST endpoints: GET /status, GET /verify/{token}."""
import jwt
from fastapi import APIRouter, HTTPException

from app.services.token import decode_token

router = APIRouter()


@router.get("/status")
async def status():
    return {"status": "ok", "service": "AgentCaptcha DPP"}


@router.get("/verify/{token}")
async def verify_token(token: str):
    """Decode and inspect a verification JWT."""
    try:
        payload = decode_token(token)
        return {"valid": True, "payload": payload}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
