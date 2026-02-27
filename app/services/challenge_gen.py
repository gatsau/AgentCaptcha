"""Claude API calls to generate and validate semantic decision challenges."""
import json
import re
from anthropic import AsyncAnthropic

from app.config import settings

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


_SCENARIOS = [
    "market_arbitrage",
    "debug_incident",
    "resource_allocation",
    "risk_assessment",
    "data_pipeline_failure",
    "api_rate_limiting",
    "cost_optimisation",
    "service_degradation",
    "security_triage",
    "capacity_planning",
]

_GEN_SYSTEM = """\
You are generating decision challenges for the Decision-Proof Protocol (DPP).
Each challenge tests whether a respondent is an autonomous AI agent capable of
rapid, consistent reasoning about operational scenarios.

Respond ONLY with valid JSON (no markdown fences) in this exact schema:
{
  "prompt": "<scenario question, 1-3 sentences>",
  "options": ["<A>", "<B>", "<C>", "<D>"],
  "correct_option": "<A|B|C|D>",
  "rationale": "<one sentence explaining the correct choice>"
}
"""

_VAL_SYSTEM = """\
You are validating an answer to an operational decision challenge.
Given the challenge JSON and the respondent's answer string, determine
whether the answer is correct or at least semantically equivalent to the
correct option.

Respond ONLY with valid JSON: {"correct": true} or {"correct": false}
"""


async def generate_challenge(
    context: dict, round_num: int, prev_answer_hash: str
) -> dict:
    """Generate one semantic challenge using Claude Haiku."""
    scenario = _SCENARIOS[(round_num - 1) % len(_SCENARIOS)]
    history_summary = (
        f"Previous {len(context.get('history', []))} rounds completed."
        if context.get("history")
        else "First round."
    )

    user_msg = (
        f"Scenario type: {scenario}\n"
        f"Round: {round_num}\n"
        f"Context: {history_summary}\n"
        f"Prev-answer-hash: {prev_answer_hash}\n"
        "Generate a new challenge for this scenario."
    )

    response = await _get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=_GEN_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )

    text = response.content[0].text.strip()
    # Strip markdown fences if model adds them despite instructions
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        challenge = json.loads(text)
    except json.JSONDecodeError:
        # Fallback minimal challenge
        challenge = {
            "prompt": f"Round {round_num}: Choose the most operationally sound action for {scenario}.",
            "options": ["A: Immediate rollback", "B: Gradual rollback", "C: Monitor only", "D: Escalate"],
            "correct_option": "A",
            "rationale": "Immediate rollback minimises blast radius.",
        }

    challenge["scenario"] = scenario
    challenge["round_num"] = round_num
    return challenge


async def validate_response(challenge: dict, answer: str, context: dict) -> bool:
    """Validate a challenge response using Claude Haiku."""
    user_msg = (
        f"Challenge: {json.dumps(challenge)}\n"
        f"Respondent answer: {answer}"
    )

    try:
        response = await _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=64,
            system=_VAL_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = response.content[0].text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        result = json.loads(text)
        return bool(result.get("correct", False))
    except Exception:
        # On any error, check for simple option match
        correct = challenge.get("correct_option", "A")
        return answer.strip().upper().startswith(correct.upper())
