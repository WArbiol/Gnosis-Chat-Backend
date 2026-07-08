from enum import Enum

from pydantic import BaseModel


class PlanEnum(str, Enum):
    FREE = "free"
    BASIC = "basic"
    PREMIUM = "premium"


class PlanLimits:
    """Centralized plan limits — single source of truth."""

    QUESTIONS: dict[PlanEnum, int] = {
        PlanEnum.FREE: 3,       # per week
        PlanEnum.BASIC: 100,    # per month
        PlanEnum.PREMIUM: 1000, # per month
    }

    INTERESTS: dict[PlanEnum, int] = {
        PlanEnum.FREE: 0,
        PlanEnum.BASIC: 20,
        PlanEnum.PREMIUM: 200,
    }

    @classmethod
    def get_question_limit(cls, plan: PlanEnum) -> int:
        return cls.QUESTIONS[plan]

    @classmethod
    def get_interest_limit(cls, plan: PlanEnum) -> int:
        return cls.INTERESTS[plan]


from datetime import datetime

class UserProfile(BaseModel):
    id: str
    email: str
    avatar_url: str | None = None
    plan: PlanEnum = PlanEnum.FREE
    chamber_level: int = 1
    question_count: int = 0
    last_reset_at: datetime | None = None
