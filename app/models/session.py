"""Session and VerificationResult dataclasses."""
from dataclasses import dataclass, field
from enum import Enum


class Verdict(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


@dataclass
class Session:
    agent_id: str
    nonce: bytes = field(default_factory=bytes)
    stage_reached: int = 0
    timings: dict = field(default_factory=dict)
    challenge_responses: list = field(default_factory=list)
    env_data: dict = field(default_factory=dict)


@dataclass
class VerificationResult:
    verdict: Verdict
    reason: str = ""
    token: str = ""
    stages_passed: list[int] = field(default_factory=list)

    @classmethod
    def accept(cls, token: str, stages_passed: list[int]) -> "VerificationResult":
        return cls(verdict=Verdict.ACCEPT, token=token, stages_passed=stages_passed)

    @classmethod
    def reject(cls, reason: str, stages_passed: list[int] | None = None) -> "VerificationResult":
        return cls(verdict=Verdict.REJECT, reason=reason, stages_passed=stages_passed or [])
