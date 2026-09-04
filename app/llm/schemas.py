from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GeminiExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_summary: str = Field(min_length=1, max_length=4000)
    technical_explanation: str = Field(min_length=1, max_length=4000)
    news_context: str = Field(min_length=1, max_length=4000)
    bull_case: str = Field(min_length=1, max_length=4000)
    bear_case: str = Field(min_length=1, max_length=4000)
    risk: str = Field(min_length=1, max_length=4000)
    conclusion: str = Field(min_length=1, max_length=4000)


PP10_MAX_SCORES: tuple[int, ...] = (10, 8, 8, 8, 8, 8, 7, 5, 6, 8, 4, 5, 5, 4, 4, 2)


class PP10AICriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: int = Field(ge=1, le=16)
    score: int = Field(ge=0, le=10)
    status: Literal["PASS", "FAIL", "DATA_UNAVAILABLE", "AI_INFERENCE"]
    assessment: str = Field(min_length=1, max_length=1200)
    data_note: str = Field(min_length=1, max_length=1200)


class PP10AIAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: str = Field(min_length=1, max_length=120)
    price_zone: str = Field(min_length=1, max_length=400)
    strategy: str = Field(min_length=1, max_length=1200)


class PP10AIReport(BaseModel):
    """AI-generated PP10 narrative; it is not a validated market signal."""

    model_config = ConfigDict(extra="forbid")

    total_score: int = Field(ge=0, le=100)
    grade: Literal["A+", "A", "B", "C"]
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    signal: Literal["TÍCH CỰC", "TRUNG TÍNH", "TIÊU CỰC", "CHƯA ĐỦ DỮ LIỆU"]
    risk: str = Field(min_length=1, max_length=120)
    preliminary_conclusion: str = Field(min_length=1, max_length=3000)
    criteria: list[PP10AICriterion] = Field(min_length=16, max_length=16)
    action_plan: list[PP10AIAction] = Field(min_length=3, max_length=3)
    conclusion_action: str = Field(min_length=1, max_length=400)
    conclusion_reason: str = Field(min_length=1, max_length=2000)
    expectation: str = Field(min_length=1, max_length=800)
    key_note: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_criteria(self) -> "PP10AIReport":
        ids = [criterion.criterion_id for criterion in self.criteria]
        if ids != list(range(1, 17)):
            raise ValueError("PP10 criteria must contain ids 1 through 16 in order")
        for criterion, maximum in zip(self.criteria, PP10_MAX_SCORES, strict=True):
            if criterion.score > maximum:
                raise ValueError(
                    f"criterion {criterion.criterion_id} score cannot exceed {maximum}"
                )
        return self
