# Phase 1 Sign-off - Swappable LLM provider + hallucination guardrails

## Scope delivered

- Pluggable LLM provider layer (`bcwatcher/llm/`): a `LLMProvider` base, an
  OpenAI-compatible provider (covers Groq/OpenAI/Azure), an Anthropic (Claude)
  provider, and a `build_provider` factory. Groq remains the default; switching
  provider is a single env var (`LLM_PROVIDER`) once a key is available.
- Config-driven, one-place secrets: `Config.llm_settings()` resolves the active
  provider (generic `LLM_*` overrides win over provider-specific values).
- Extract -> validate -> render guardrails (`bcwatcher/guardrails.py`):
  - temperature 0 and bounded payloads/output for determinism and low tokens,
  - length caps, whitespace/quote/markdown cleanup, em/en dash removal,
  - grounding: fabricated Jira keys are rejected (short fields fall back to
    "Not stated in ticket"; RCA HTML keys are neutralised),
  - HTML reduced to an allow-list of attribute-less tags (no links/scripts/
    styles/handlers).
- `summarizer.py` refactored onto the provider + guardrails; transport/parse
  failures raise `LLMError` so the scan retries the case instead of emitting
  empty or invented content.

## Verification (local)

- `ruff check .` - all checks passed.
- `pytest` - full suite green (guardrails, provider factory/parsing/errors,
  summarizer validation, plus the existing Phase 0 tests).

## Acceptance checklist

- [ ] Provider swaps to OpenAI/Anthropic with only env changes (no code edits).
- [ ] Guardrails reject ungrounded keys and unsafe HTML in review.
- [ ] Token usage / output bounds confirmed acceptable on real tickets.

## Sign-off

- Engineering lead: ________________   Date: _______
- Product owner:   ________________   Date: _______

After both sign-offs, tag the commit `phase-1-signed`.
