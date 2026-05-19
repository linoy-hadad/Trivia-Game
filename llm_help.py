from __future__ import annotations

import os


FALLBACKS = [
    "Your friend squints at the options and says: trust the answer that feels least dramatic.",
    "Your friend says: I am not betting the rent, but this one has strong correct-answer energy.",
    "Your friend whispers: eliminate the weirdest option first, then follow the clue in the wording.",
]


async def get_friend_advice(question: str, options: list[dict[str, str]]) -> str:
    if not os.getenv("OPENAI_API_KEY"):
        return _fallback_advice(question, options)

    try:
        from pydantic_ai import Agent

        model = os.getenv("PYDANTIC_AI_MODEL", "openai:gpt-5.2")
        agent = Agent(
            model,
            system_prompt=(
                "You are a funny trivia lifeline friend. Give playful, concise advice. "
                "Do not reveal certainty unless the evidence is strong. Max 45 words."
            ),
        )
        option_text = "\n".join(f"- {option['text']}" for option in options)
        result = await agent.run(f"Question: {question}\nOptions:\n{option_text}")
        return str(result.output).strip()
    except Exception:
        return _fallback_advice(question, options)


def _fallback_advice(question: str, options: list[dict[str, str]]) -> str:
    seed = len(question) + sum(len(option["text"]) for option in options)
    return FALLBACKS[seed % len(FALLBACKS)]
