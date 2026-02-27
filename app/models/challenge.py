"""Challenge, Response, and Stage dataclasses."""
from dataclasses import dataclass
from enum import IntEnum


class Stage(IntEnum):
    POW = 1
    DECISIONS = 2
    ENVIRONMENT = 3
    CONSISTENCY = 4


@dataclass
class Challenge:
    stage: Stage
    round_num: int
    prompt: str
    context: dict
    prev_answer_hash: str = ""


@dataclass
class ChallengeResponse:
    round_num: int
    answer: str
    elapsed_s: float
    correct: bool = False
