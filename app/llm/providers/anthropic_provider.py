"""Anthropic provider — port of server/llm/providers/anthropic.ts.

Uses tool-use to coerce structured output, mirroring the TS implementation.
"""

from __future__ import annotations

from typing import Any, TypeVar

from anthropic import AsyncAnthropic
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def _pydantic_to_input_schema(schema: type[BaseModel]) -> dict[str, Any]:
    raw = schema.model_json_schema()
    defs = raw.pop("$defs", None) or raw.pop("definitions", None)

    def inline(node: Any) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and defs:
                key = ref.rsplit("/", 1)[-1]
                target = defs.get(key)
                if target is not None:
                    merged = {k: v for k, v in node.items() if k != "$ref"}
                    return inline({**target, **merged})
            return {k: inline(v) for k, v in node.items()}
        if isinstance(node, list):
            return [inline(v) for v in node]
        return node

    return inline(raw)


class AnthropicProvider:
    def __init__(self, api_key: str, default_model: str) -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._default_model = default_model

    async def extract_structured(
        self,
        *,
        schema: type[T],
        prompt: str,
        text: str,
        model: str | None = None,
    ) -> T:
        input_schema = _pydantic_to_input_schema(schema)
        response = await self._client.messages.create(
            model=model or self._default_model,
            max_tokens=4096,
            system=prompt,
            messages=[{"role": "user", "content": text}],
            tools=[
                {
                    "name": "extraction",
                    "description": "Extract structured data from the text",
                    "input_schema": input_schema,
                }
            ],
            tool_choice={"type": "tool", "name": "extraction"},
        )

        tool_block = next(
            (block for block in response.content if getattr(block, "type", None) == "tool_use"),
            None,
        )
        if tool_block is None:
            raise RuntimeError("Anthropic returned no tool use block")

        return schema.model_validate(tool_block.input)


def create_anthropic_client(api_key: str, default_model: str) -> AnthropicProvider:
    return AnthropicProvider(api_key, default_model)
