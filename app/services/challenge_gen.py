"""Challenge generation and validation — Claude API with static fallback."""
import json
import logging
import random
import re

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static challenge bank (used when ANTHROPIC_API_KEY is not set)
# ---------------------------------------------------------------------------

_STATIC_CHALLENGES = [
    {
        "prompt": "A market-making bot detects a 0.4% price discrepancy between two exchanges. Transaction fees are 0.1% per leg. What is the correct action?",
        "options": ["A: Execute immediately — 0.2% net profit after fees", "B: Wait for a wider spread to increase margin", "C: Cancel all open orders first to reduce exposure", "D: Alert a human trader and await confirmation"],
        "correct_option": "A",
        "rationale": "0.4% spread minus 0.2% total fees yields a positive expected value; immediate execution captures the arbitrage.",
    },
    {
        "prompt": "A microservice returns HTTP 503 intermittently. p99 latency has jumped from 120ms to 4200ms. CPU is at 15%. What should you do first?",
        "options": ["A: Restart the service immediately", "B: Check connection pool exhaustion and downstream dependency health", "C: Scale horizontally and add more instances", "D: Roll back the last deployment"],
        "correct_option": "B",
        "rationale": "Low CPU with high latency and 503s points to a downstream bottleneck or pool exhaustion, not CPU pressure.",
    },
    {
        "prompt": "You have a $10k compute budget for a batch ML job. Spot instances cost $0.30/hr but have a 15% interruption rate. On-demand costs $1.20/hr. The job takes ~100 hrs. Which is cheaper in expectation?",
        "options": ["A: On-demand — $120 total, predictable", "B: Spot — ~$34.50 expected cost even with retries", "C: Mix 50/50 for risk reduction", "D: Use preemptible VMs on a different cloud"],
        "correct_option": "B",
        "rationale": "Expected spot cost including ~15% retry overhead is ~$34.50, far below the $120 on-demand price.",
    },
    {
        "prompt": "A data pipeline ingesting 500k events/sec suddenly drops to 50k/sec. Kafka consumer lag is growing at 1M messages/min. No errors in logs. What is the most likely cause?",
        "options": ["A: Network partition between broker and consumers", "B: Consumer rebalance triggered by a new deployment", "C: Disk I/O saturation on broker nodes", "D: Schema registry outage blocking deserialization"],
        "correct_option": "B",
        "rationale": "A drop without errors combined with timing of deployment strongly suggests a consumer group rebalance pause.",
    },
    {
        "prompt": "Your API is hitting a 3rd-party rate limit of 1000 req/min. You currently send requests at 1100 req/min with no queuing. What is the best fix?",
        "options": ["A: Add a token bucket limiter at 950 req/min with a backpressure queue", "B: Retry failed requests with exponential backoff only", "C: Distribute requests across multiple API keys", "D: Cache all responses for 60 seconds"],
        "correct_option": "A",
        "rationale": "A token bucket below the limit with backpressure prevents rate-limit errors while maintaining throughput.",
    },
    {
        "prompt": "A security scan finds an open S3 bucket containing logs with PII. The bucket has had public access for 72 hours. What is the correct first action?",
        "options": ["A: Delete the bucket immediately", "B: Block public access, then assess what data was exposed", "C: Rotate all IAM credentials immediately", "D: Notify customers before taking any action"],
        "correct_option": "B",
        "rationale": "Blocking access stops the breach immediately; assessment must precede deletion to preserve evidence and scope the impact.",
    },
    {
        "prompt": "A Redis cache cluster is at 98% memory utilisation. Eviction policy is set to noeviction. What happens on the next write?",
        "options": ["A: Redis silently drops the oldest key", "B: Redis returns an OOM error to the client", "C: Redis automatically expands its memory allocation", "D: Redis writes to disk and clears memory"],
        "correct_option": "B",
        "rationale": "noeviction causes Redis to return an error rather than evict keys, breaking writes when memory is full.",
    },
    {
        "prompt": "You need to run 1000 independent 10-second tasks. You have 50 workers. What is the minimum theoretical completion time?",
        "options": ["A: 10 seconds", "B: 200 seconds", "C: 500 seconds", "D: 10000 seconds"],
        "correct_option": "B",
        "rationale": "1000 tasks / 50 workers = 20 batches × 10 seconds = 200 seconds minimum with perfect parallelism.",
    },
    {
        "prompt": "A Postgres query doing a full table scan on a 50M-row table runs in 45 seconds. Adding an index on the filter column brings it to 80ms. What is the approximate speedup factor?",
        "options": ["A: 56x", "B: 562x", "C: 5625x", "D: 56250x"],
        "correct_option": "B",
        "rationale": "45000ms / 80ms = 562.5x speedup.",
    },
    {
        "prompt": "A deployment pipeline runs 400 unit tests in 18 minutes on a single runner. You need to get this under 3 minutes. What is the minimum number of parallel runners required?",
        "options": ["A: 3", "B: 6", "C: 7", "D: 10"],
        "correct_option": "C",
        "rationale": "18 / 3 = 6.0, but since you need strictly under 3 minutes, you need 7 runners (18/7 ≈ 2.57 min).",
    },
    {
        "prompt": "Service A calls Service B synchronously. Service B has a 2% error rate and 200ms p99. You add a circuit breaker that opens after 5 consecutive errors. What does this prevent?",
        "options": ["A: All errors from Service B", "B: Cascading failures where A's thread pool exhausts waiting for a broken B", "C: Network partitions between A and B", "D: Memory leaks in Service A"],
        "correct_option": "B",
        "rationale": "Circuit breakers prevent cascading failure by fast-failing calls to a known-broken dependency, protecting upstream thread pools.",
    },
    {
        "prompt": "A canary deployment shows the new version has 0.8% error rate vs 0.1% baseline. Traffic split is 5% canary / 95% stable. What is the correct action?",
        "options": ["A: Roll back immediately — 8x error rate increase", "B: Continue rollout — absolute error rate is still below 1%", "C: Pause and investigate the error pattern before deciding", "D: Increase canary traffic to 50% to get better signal"],
        "correct_option": "C",
        "rationale": "An 8x relative increase warrants investigation before rollback or promotion — the error type matters for the decision.",
    },
]


# ---------------------------------------------------------------------------
# Claude API client (lazy init)
# ---------------------------------------------------------------------------

_claude_client = None


def _get_claude_client():
    global _claude_client
    if _claude_client is None:
        from anthropic import AsyncAnthropic
        _claude_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _claude_client


_SCENARIOS = [
    "market_arbitrage", "debug_incident", "resource_allocation",
    "risk_assessment", "data_pipeline_failure", "api_rate_limiting",
    "cost_optimisation", "service_degradation", "security_triage",
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate_challenge(
    context: dict, round_num: int, prev_answer_hash: str
) -> dict:
    """Generate one challenge — uses Claude if API key is set, else static bank."""
    if settings.use_mock_challenges:
        return _static_challenge(round_num)
    return await _claude_challenge(context, round_num, prev_answer_hash)


async def validate_response(challenge: dict, answer: str, context: dict) -> bool:
    """Validate a response — uses Claude if API key is set, else letter-match."""
    if settings.use_mock_challenges:
        return _static_validate(challenge, answer)
    return await _claude_validate(challenge, answer)


# ---------------------------------------------------------------------------
# Static implementations
# ---------------------------------------------------------------------------

def _static_challenge(round_num: int) -> dict:
    idx = (round_num - 1) % len(_STATIC_CHALLENGES)
    ch = dict(_STATIC_CHALLENGES[idx])
    ch["round_num"] = round_num
    ch["scenario"] = _SCENARIOS[(round_num - 1) % len(_SCENARIOS)]
    return ch


def _static_validate(challenge: dict, answer: str) -> bool:
    correct = challenge.get("correct_option", "A").strip().upper()[0]
    # Accept if the answer starts with the correct letter (with or without colon)
    stripped = answer.strip().upper()
    return stripped.startswith(correct)


# ---------------------------------------------------------------------------
# Claude implementations
# ---------------------------------------------------------------------------

async def _claude_challenge(context: dict, round_num: int, prev_answer_hash: str) -> dict:
    scenario = _SCENARIOS[(round_num - 1) % len(_SCENARIOS)]
    history_summary = (
        f"Previous {len(context.get('history', []))} rounds completed."
        if context.get("history") else "First round."
    )
    user_msg = (
        f"Scenario type: {scenario}\n"
        f"Round: {round_num}\n"
        f"Context: {history_summary}\n"
        f"Prev-answer-hash: {prev_answer_hash}\n"
        "Generate a new challenge."
    )
    try:
        response = await _get_claude_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=_GEN_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = _strip_fences(response.content[0].text)
        challenge = json.loads(text)
    except Exception as exc:
        logger.warning("Claude challenge generation failed (%s), using static fallback", exc)
        return _static_challenge(round_num)

    challenge["scenario"] = scenario
    challenge["round_num"] = round_num
    return challenge


async def _claude_validate(challenge: dict, answer: str) -> bool:
    user_msg = (
        f"Challenge: {json.dumps(challenge)}\n"
        f"Respondent answer: {answer}"
    )
    try:
        response = await _get_claude_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=64,
            system=_VAL_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = _strip_fences(response.content[0].text)
        result = json.loads(text)
        return bool(result.get("correct", False))
    except Exception:
        return _static_validate(challenge, answer)


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text
