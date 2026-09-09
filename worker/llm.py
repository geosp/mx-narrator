"""Generic LLM harness for metadata generation — see design.md's Decisions.

One function, one schema. No agent framework, no tool use: `generate_structured()`
makes a single structured completion call via LiteLLM, whose `model` string prefix
(`ollama_chat/`, `hosted_vllm/`, `anthropic/`, ...) is the entire provider-switch
surface — swapping providers or target machines is a config change, not a code change.
"""

from __future__ import annotations

import os

import litellm
from pydantic import BaseModel, Field

# ollama_chat/, not ollama/ — confirmed by reading litellm's own provider code
# (llms/ollama/completion/transformation.py vs llms/ollama/chat/transformation.py):
# the plain "ollama/" prefix routes through Ollama's legacy /api/generate handler,
# whose transform_request() dumps keep_alive into the wrong place (Ollama's
# per-request "options" dict, which Ollama silently ignores it in) instead of the
# top-level request field Ollama actually reads it from — verified for real: a
# keep_alive kwarg sent via "ollama/..." left `ollama ps`'s UNTIL unchanged from
# the 5-minute default. "ollama_chat/" uses /api/chat and handles keep_alive (and
# response_format) correctly — verified the same way, UNTIL reflected the real value.
LLM_MODEL = os.environ.get("LLM_MODEL", "ollama_chat/qwen3.5:9b")
LLM_API_BASE = os.environ.get("LLM_API_BASE")
# Ollama unloads an idle model after 5 minutes by default, forcing a fresh
# runner (re)start on the next call — real journalctl evidence (see
# GENERATE_METADATA_RETRY_POLICY's comment in worker/workflows.py) shows this
# deployment's intermittent ROCm GPU-hang correlates with runner (re)starts,
# not idle time itself. A longer keep_alive means fewer cold starts, and
# fewer cold starts means fewer chances to hit it. No effect on non-Ollama
# providers (see generate_structured()).
OLLAMA_KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")


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
    # keep_alive/think are Ollama-only concepts — passing them to another provider
    # (e.g. anthropic/...) would be meaningless, so only set them for that one.
    # think=False matters for real: verified against qwen3.5:9b (a "thinking" model)
    # on a real production script — left at its default, it burns 1500+ completion
    # tokens on internal reasoning before answering, which pushed past Ollama's
    # default 4096-token context window and produced either empty content (a JSON
    # parse failure) or syntactically valid but *wrong* content (a fully unrelated,
    # English-language answer for a Spanish-language episode). With think=False the
    # same real script produced a correct, on-topic, appropriately-Spanish answer in
    # ~250 completion tokens. Harmless no-op for llama3.1:8b (not a thinking model).
    extra_kwargs = {"keep_alive": OLLAMA_KEEP_ALIVE, "think": False} if LLM_MODEL.startswith("ollama") else {}
    response = await litellm.acompletion(
        model=LLM_MODEL,
        base_url=LLM_API_BASE,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        response_format=response_format,
        **extra_kwargs,
    )
    content = response.choices[0].message.content
    return schema.model_validate_json(content)
