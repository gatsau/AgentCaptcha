"""Stage 2: 10-round semantic decision challenges via Claude API."""
import asyncio
import hashlib
import time

from app.config import settings
from app.models.challenge import ChallengeResponse, Stage
from app.models.session import Session, VerificationResult
from app.services.challenge_gen import generate_challenge, validate_response


async def run(session: Session, ws_send, ws_recv) -> VerificationResult | None:
    """
    Run DECISION_ROUNDS rounds of semantic challenges.
    Checks timing variance (CV) after all rounds.
    Returns None on success, VerificationResult.reject on failure.
    """
    responses: list[ChallengeResponse] = []
    prev_answer_hash = ""
    context = {"agent_id": session.agent_id, "history": []}

    for round_num in range(1, settings.decision_rounds + 1):
        challenge = await generate_challenge(context, round_num, prev_answer_hash)

        await ws_send({
            "stage": 2,
            "type": "decision_challenge",
            "round": round_num,
            "total_rounds": settings.decision_rounds,
            "prompt": challenge["prompt"],
            "options": challenge.get("options", []),
            "prev_answer_hash": prev_answer_hash,
        })

        t0 = time.perf_counter()
        try:
            msg = await asyncio.wait_for(
                ws_recv(), timeout=settings.decision_timeout_s
            )
        except asyncio.TimeoutError:
            session.timings["stage2"] = time.perf_counter() - t0
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

        prev_answer_hash = hashlib.sha256(answer.encode()).hexdigest()[:16]
        context["history"].append({
            "round": round_num,
            "prompt": challenge["prompt"],
            "answer": answer,
            "correct": correct,
        })

    # Timing variance check: coefficient of variation > 0.4 → likely human
    timings = [r.elapsed_s for r in responses]
    mean = sum(timings) / len(timings)
    if mean > 0:
        std = (sum((t - mean) ** 2 for t in timings) / len(timings)) ** 0.5
        cv = std / mean
    else:
        cv = 0.0

    session.timings["stage2_cv"] = cv
    session.timings["stage2"] = sum(timings)

    if cv > 0.4:
        return VerificationResult.reject(f"stage2_timing_variance_cv={cv:.3f}")

    correct_count = sum(1 for r in responses if r.correct)
    if correct_count < settings.decision_rounds * 0.7:
        return VerificationResult.reject(
            f"stage2_low_accuracy_{correct_count}/{settings.decision_rounds}"
        )

    session.stage_reached = 2
    return None
