"""OpenAI provider — port of server/llm/providers/openai.ts."""

from __future__ import annotations

from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class OpenAIProvider:
    def __init__(self, api_key: str, default_model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._default_model = default_model

    async def extract_structured(
        self,
        *,
        schema: type[T],
        prompt: str,
        text: str,
        model: str | None = None,
    ) -> T:
        response = await self._client.chat.completions.parse(
            model=model or self._default_model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
            response_format=schema,
        )

        parsed = response.choices[0].message.parsed if response.choices else None
        if parsed is None:
            raise RuntimeError("OpenAI returned no parsed structured output")
        return parsed


def create_openai_client(api_key: str, default_model: str) -> OpenAIProvider:
    return OpenAIProvider(api_key, default_model)
