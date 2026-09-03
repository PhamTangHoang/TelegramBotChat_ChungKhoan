from pydantic import BaseModel, ConfigDict, Field


class GeminiExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_summary: str = Field(min_length=1, max_length=4000)
    technical_explanation: str = Field(min_length=1, max_length=4000)
    news_context: str = Field(min_length=1, max_length=4000)
    bull_case: str = Field(min_length=1, max_length=4000)
    bear_case: str = Field(min_length=1, max_length=4000)
    risk: str = Field(min_length=1, max_length=4000)
    conclusion: str = Field(min_length=1, max_length=4000)
