from __future__ import annotations

from typing import Any

from app.audit.snapshot import canonical_json

PROMPT_VERSION = "1.0.0"

SYSTEM_INSTRUCTION = """You explain a precomputed Vietnamese stock technical analysis.
The Rule Engine is authoritative. Do not recalculate indicators, change the signal,
change the score, change the risk, or turn INSUFFICIENT_DATA into a signal.
Use news only as context. Explicitly distinguish news published_at from market as_of.
The conclusion must agree with the primary signal supplied in Decision Context.
This is a private analytical tool, not investment advice, and score is not a
probability estimate or validated confidence percentage.
Return only the requested structured JSON object."""

CHAT_SYSTEM_INSTRUCTION = """You are the conversational assistant inside VN Stock Analyst Bot.
Answer in concise Vietnamese unless the user asks for another language. You can
explain how the bot works, stock-analysis concepts and the available commands.
Do not invent current prices, market status or news. For a live technical report,
ask the user to use /pt SYMBOL or /chart SYMBOL. Do not give personalized buy,
sell or hold instructions. Keep the response educational and include a brief
disclaimer when the user asks for an investment decision. Return plain text."""


def build_prompt(
    *,
    quantitative_context: Any,
    event_context: Any,
    decision_context: Any,
) -> str:
    return "\n".join(
        (
            SYSTEM_INSTRUCTION,
            "\nQuantitative Context:\n" + canonical_json(quantitative_context),
            "\nEvent Context:\n" + canonical_json(event_context),
            "\nDecision Context:\n" + canonical_json(decision_context),
        )
    )


def build_chat_prompt(message: str) -> str:
    return "\n".join(
        (
            CHAT_SYSTEM_INSTRUCTION,
            "\nUser message:\n---\n" + message.strip()[:2000] + "\n---",
        )
    )
