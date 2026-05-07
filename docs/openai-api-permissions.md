# OpenAI API key permissions

When using OpenAI as the LLM provider (default), the API key needs the following capabilities. These match what the original TS port required.

## Required scopes

- **Model: write/respond** — for `chat.completions.parse` (structured output via Pydantic).

## Recommended setup

1. Create a [Project API key](https://platform.openai.com/api-keys) restricted to a single project.
2. Set the **role** to **All** for the model API.
3. Cap the project's monthly spend in **Settings → Billing**.
4. Set `LLM_API_KEY` on the `sf-pulse-python-env` env group.

## Anthropic alternative

To use Anthropic instead, set `LLM_API_KEY` to a key that begins with `sk-ant-`. The factory auto-detects the provider from the prefix; no other config is needed.

The Anthropic provider uses tool-use to coerce structured output. Models that support tool use (`claude-3-5-sonnet`, `claude-3-5-haiku`, `claude-haiku-4-5`, etc.) work out of the box. Set `LLM_MODEL` to override the default.
