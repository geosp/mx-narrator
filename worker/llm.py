"""Generic LLM harness for metadata generation — see design.md's Decisions.

One function, one schema. No agent framework, no tool use: `generate_structured()`
makes a single structured completion call via LiteLLM, whose `model` string prefix
(`ollama/`, `hosted_vllm/`, `anthropic/`, ...) is the entire provider-switch surface —
swapping providers or target machines is a config change, not a code change.
"""

from __future__ import annotations

import os

import litellm
from pydantic import BaseModel, Field

LLM_MODEL = os.environ.get("LLM_MODEL", "ollama/llama3.1:8b")
LLM_API_BASE = os.environ.get("LLM_API_BASE")


class VideoMetadataSchema(BaseModel):
    # YouTube's own length caps, enforced here so a schema violation is caught before
    # ever reaching a human reviewer, not just left to whatever the model produces.
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=5000)
    tags: list[str] = Field(min_length=1, max_length=30)


async def generate_structured(*, system: str, prompt: str, schema: type[BaseModel]) -> BaseModel:
    # Passed as an explicit json_schema dict, not the raw Pydantic class — LiteLLM has
    # documented inconsistency issues with the latter across providers (design.md).
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": schema.__name__,
            "schema": schema.model_json_schema(),
            "strict": True,
        },
    }
    response = await litellm.acompletion(
        model=LLM_MODEL,
        base_url=LLM_API_BASE,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        response_format=response_format,
    )
    content = response.choices[0].message.content
    return schema.model_validate_json(content)
