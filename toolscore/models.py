"""Current default model IDs, in one place.

Toolscore itself never calls a model; these IDs are the defaults for the
optional LLM judge (``toolscore eval --llm-judge``) and the examples, scaffolds
and docs. Provider model lists change often, so every value here was checked
against the provider's official documentation on the date below. Update them
together, with the date.

Verified 2026-11-01 against:

* Anthropic: https://platform.claude.com/docs/en/about-claude/models/overview
* OpenAI: https://developers.openai.com/api/docs/models
* Google: https://ai.google.dev/gemini-api/docs/models

Current Anthropic models (Opus 4.7 and later, Sonnet 5 and later, Haiku 5.5)
and OpenAI's GPT-6 models at their default reasoning effort reject a
non-default ``temperature``, so the judge sends none unless asked to.
"""

from __future__ import annotations

#: Date the IDs below were last checked against the providers' docs.
VERIFIED_ON = "2026-11-01"

#: OpenAI's model for cost-sensitive, high-volume work; the default judge.
OPENAI_DEFAULT = "gpt-6-luna"
#: OpenAI's balanced model.
OPENAI_BALANCED = "gpt-6.1-sol"

#: Anthropic's fastest, cheapest current model.
ANTHROPIC_FAST = "claude-haiku-5-5"
#: Anthropic's balanced current model (a stronger judge).
ANTHROPIC_BALANCED = "claude-sonnet-5-5"
#: Anthropic's most capable Opus model.
ANTHROPIC_TOP = "claude-opus-5-5"

#: Google's low-cost current Gemini model.
GEMINI_DEFAULT = "gemini-3.5-flash-lite"

#: The LLM judge's default model.
DEFAULT_JUDGE_MODEL = OPENAI_DEFAULT

__all__ = [
    "ANTHROPIC_BALANCED",
    "ANTHROPIC_FAST",
    "ANTHROPIC_TOP",
    "DEFAULT_JUDGE_MODEL",
    "GEMINI_DEFAULT",
    "OPENAI_BALANCED",
    "OPENAI_DEFAULT",
    "VERIFIED_ON",
]
