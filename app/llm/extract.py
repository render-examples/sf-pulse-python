"""Single-call extraction wrapper with one-shot retry — port of server/llm/extract.ts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    pass

T = TypeVar("T", bound=BaseModel)


class LLMClient(Protocol):
    async def extract_structured(
        self,
        *,
        schema: type[T],
        prompt: str,
        text: str,
        model: str | None = None,
    ) -> T: ...


async def extract_structured(
    client: LLMClient,
    *,
    schema: type[T],
    prompt: str,
    text: str,
    model: str | None = None,
) -> T | None:
    try:
        return await client.extract_structured(
            schema=schema, prompt=prompt, text=text, model=model
        )
    except Exception as first_error:
        print(f"[llm] extraction failed, retrying with simplified prompt: {first_error}")
        try:
            return await client.extract_structured(
                schema=schema,
                prompt=f"{prompt}\n\nRespond with valid JSON matching the schema. Be concise.",
                text=text,
                model=model,
            )
        except Exception as retry_error:
            print(f"[llm] retry also failed, skipping: {retry_error}")
            return None
