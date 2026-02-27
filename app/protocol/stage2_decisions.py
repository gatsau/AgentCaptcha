"""Stage 2: 10-round semantic decision challenges via Claude API."""
import asyncio
import hashlib
import logging
import time

from app.config import settings
from app.models.challenge import ChallengeResponse
from app.models.session import Session, VerificationResult
from app.services.challenge_gen import generate_challenge, validate_response

logger = logging.getLogger(__name__)

# CV threshold: reject if timing is too erratic (human-like inconsistency).
# Set at 0.8 to accommodate agents calling external APIs with moderate network jitter.
_CV_REJECT_THRESHOLD = 0.8


async def run(
    session: Session,
    ws_send,
    ws_recv,
    session_id: int | None = None,
) -> VerificationResult | None:
    """
    Run DECISION_ROUNDS rounds of semantic challenges.
    Persists each round to challenge_history if session_id is provided.
    Returns None on success, VerificationResult.reject on failure.
    """
    from app.database import insert_challenge_history

    responses: list[ChallengeResponse] = []
    prev_answer_hash = ""
    context = {"agent_id": session.agent_id, "history": []}

    for round_num in range(1, settings.decision_rounds + 1):
        challenge = await generate_challenge(context, round_num, prev_answer_hash)

        payload: dict = {
            "stage": 2,
            "type": "decision_challenge",
            "round": round_num,
            "total_rounds": settings.decision_rounds,
            "prompt": challenge["prompt"],
            "options": challenge.get("options", []),
            "prev_answer_hash": prev_answer_hash,
        }
        # In mock mode (no API key), include the correct option so demo clients
        # can respond correctly without a Claude key.
        if settings.use_mock_challenges:
            payload["mock_correct"] = challenge.get("correct_option", "A")
        await ws_send(payload)

        t0 = time.perf_counter()
        try:
            msg = await asyncio.wait_for(
                ws_recv(), timeout=settings.decision_timeout_s
            )
        except asyncio.TimeoutError:
            elapsed = time.perf_counter() - t0
            session.timings["stage2"] = elapsed
            return VerificationResult.reject(f"stage2_timeout_round{round_num}")

        elapsed = time.perf_counter() - t0
        answer = msg.get("answer", "")

        correct = await validate_response(challenge, answer, context)
        resp = ChallengeResponse(
            round_num=round_num,
            answer=answer,
            elapsed_s=elapsed,
            correct=correct,
        )
        responses.append(resp)
        session.challenge_responses.append(resp)

        # Persist to DB
        if session_id is not None:
            try:
                await insert_challenge_history(
                    session_id=session_id,
                    round_num=round_num,
                    challenge_text=challenge["prompt"],
                    response_text=answer,
                    correct=correct,
                    response_time_s=elapsed,
                )
            except Exception as exc:
                logger.warning("Failed to persist challenge_history round %d: %s", round_num, exc)

        prev_answer_hash = hashlib.sha256(answer.encode()).hexdigest()[:16]
        context["history"].append({
            "round": round_num,
            "prompt": challenge["prompt"],
            "answer": answer,
            "correct": correct,
        })

    # Timing variance check
    timings = [r.elapsed_s for r in responses]
    mean = sum(timings) / len(timings)
    if mean > 0:
        std = (sum((t - mean) ** 2 for t in timings) / len(timings)) ** 0.5
        cv = std / mean
    else:
        cv = 0.0

    session.timings["stage2_cv"] = cv
    session.timings["stage2"] = sum(timings)
    session.timings["stage2_mean_s"] = mean

    if cv > _CV_REJECT_THRESHOLD:
        return VerificationResult.reject(f"stage2_timing_variance_cv={cv:.3f}")

    correct_count = sum(1 for r in responses if r.correct)
    if correct_count < settings.decision_rounds * 0.7:
        return VerificationResult.reject(
            f"stage2_low_accuracy_{correct_count}/{settings.decision_rounds}"
        )

    session.stage_reached = 2
    return None
