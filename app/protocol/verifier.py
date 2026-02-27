"""Orchestrates all 4 verification stages and persists results."""
import time
import uuid

from app.database import insert_session
from app.models.session import Session, VerificationResult, Verdict
from app.protocol import stage1_pow, stage2_decisions, stage3_environment, stage4_consistency
from app.services.token import create_token


async def verify(ws_send, ws_recv, agent_id: str | None = None) -> VerificationResult:
    """
    Run the full DPP verification protocol over a WebSocket connection.
    Persists the session and returns a VerificationResult.
    """
    agent_id = agent_id or str(uuid.uuid4())
    session = Session(agent_id=agent_id)
    timestamp = time.time()
    stages_passed: list[int] = []

    # Pre-create a session row so Stage 2 can write challenge_history against it.
    # We'll update it at the end — for now record stage 0, not passed.
    session_id = await insert_session(
        agent_id=agent_id,
        stage_reached=0,
        timestamp=timestamp,
        timings={},
        passed=False,
        reject_reason="in_progress",
    )

    async def _reject(result: VerificationResult) -> VerificationResult:
        await ws_send({"type": "result", "verdict": "REJECT", "reason": result.reason})
        await _update_session(session_id, session, passed=False, reject_reason=result.reason)
        return result

    # Stage 1 — Proof of Work
    result = await stage1_pow.run(session, ws_send, ws_recv)
    if result is not None:
        return await _reject(result)
    stages_passed.append(1)

    # Stage 2 — Semantic decision challenges (passes session_id for history writes)
    result = await stage2_decisions.run(session, ws_send, ws_recv, session_id=session_id)
    if result is not None:
        return await _reject(result)
    stages_passed.append(2)

    # Stage 3 — Environment attestation
    result = await stage3_environment.run(session, ws_send, ws_recv)
    if result is not None:
        return await _reject(result)
    stages_passed.append(3)

    # Stage 4 — Cross-session consistency
    result = await stage4_consistency.run(session)
    if result is not None:
        return await _reject(result)
    stages_passed.append(4)

    token = create_token(agent_id=agent_id, stages_passed=stages_passed)

    await _update_session(session_id, session, passed=True, reject_reason=None)

    await ws_send({
        "type": "result",
        "verdict": "ACCEPT",
        "token": token,
        "stages_passed": stages_passed,
    })

    return VerificationResult.accept(token=token, stages_passed=stages_passed)


async def _update_session(
    session_id: int,
    session: Session,
    passed: bool,
    reject_reason: str | None,
) -> None:
    """Overwrite the pre-created session row with final state."""
    import json
    from app.database import get_db
    db = await get_db()
    await db.execute(
        """UPDATE sessions
           SET stage_reached=?, timings=?, passed=?, reject_reason=?
           WHERE id=?""",
        (
            session.stage_reached,
            json.dumps(session.timings),
            int(passed),
            reject_reason,
            session_id,
        ),
    )
    await db.commit()
