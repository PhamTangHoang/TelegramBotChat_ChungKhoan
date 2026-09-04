from app.llm.prompts import build_chat_prompt, build_prompt


def test_analysis_prompt_requires_vietnamese_user_facing_text() -> None:
    prompt = build_prompt(
        quantitative_context={"rsi14": 60},
        event_context=[],
        decision_context={"signal": "NEUTRAL"},
    )

    assert "every user-facing field in Vietnamese" in prompt
    assert "Do not output English prose" in prompt


def test_chat_prompt_requires_vietnamese_without_language_switch() -> None:
    prompt = build_chat_prompt("Xin chào")

    assert "Always answer in Vietnamese" in prompt
    assert "Do not switch to English" in prompt
    assert "unless the user asks for another language" not in prompt
