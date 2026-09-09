"""Metadata-generation logic (LLM title/description/tags), split out of
worker/activities.py so `api/main.py` can call it directly.

`worker/activities.py` imports `mx_narrator.batch` at module level (pulling in
the full ML stack — torch, Chatterbox, etc.); `api/main.py` deliberately never
imports `worker.activities`/`worker.workflows` for exactly that reason, to keep
the API process's startup light even though the underlying dependencies are
present in the same Docker image. This module has no such import, so it's safe
for both `worker/activities.py`'s `generate_metadata` Activity and `api/main.py`'s
"regenerate" endpoint to call the same real logic directly.
"""

from __future__ import annotations

from worker.llm import VideoMetadataSchema, generate_structured
from worker.types import VideoMetadataFields

# Prior human-approved episode titles for the same series, prompt context for
# consistency — capped so a long-running series doesn't grow the prompt unbounded.
SERIES_CONTEXT_LIMIT = 10

# YouTube's own soft guideline for a title's length, used only to steer the
# prompt — NOT enforced by truncation. Truncating the subtitle to fit was
# tried and reverted: measured 6 real, unconstrained subtitles the model
# wrote for one real episode and every single one (77-101 chars) already
# exceeded that episode's available budget, so truncation was the normal
# case, not a rare backstop — and even word-boundary-aware truncation kept
# landing on a grammatically dangling preposition/conjunction ("...con
# Dios, la", "...capellán como"), which read as more broken than a longer
# title does. A human reviews every title before it's ever used, so a
# slightly-over-100-characters title is a minor, easily-edited cosmetic
# issue; a truncated one that reads as an unfinished sentence is worse.
YOUTUBE_TITLE_GUIDELINE_LENGTH = 100
TITLE_SEPARATOR = " | "


def _compose_title(unit_id: str, subtitle: str) -> str:
    return f"{unit_id}{TITLE_SEPARATOR}{subtitle}"


async def fetch_series_context(db, script_id: str) -> list[str]:
    """Prior human-approved episode titles for the same series, most recent
    first. Draft/unapproved titles are excluded. Returns [] for a script with
    no `series_name` set, rather than erroring — `POST /scripts` doesn't
    currently collect `series_name` at all, so this is the common case today,
    not just an edge case."""
    script = await db["scripts"].find_one({"_id": script_id})
    if script is None or not script.get("series_name"):
        return []

    series_name = script["series_name"]
    titles: list[tuple] = []
    async for sibling in db["scripts"].find({"series_name": series_name, "_id": {"$ne": script_id}}):
        render_job_doc = await db["render_jobs"].find_one(
            {"script_id": sibling["_id"]}, sort=[("created_at", -1)]
        )
        if render_job_doc is None:
            continue
        video_job = await db["video_jobs"].find_one(
            {"render_job_id": render_job_doc["_id"]}, sort=[("created_at", -1)]
        )
        if video_job is None:
            continue
        metadata = await db["video_metadata"].find_one(
            {"video_job_id": video_job["_id"], "human_approved_at": {"$ne": None}}
        )
        if metadata is None:
            continue
        titles.append((metadata["human_approved_at"], metadata["generated_title"]))

    titles.sort(key=lambda t: t[0], reverse=True)
    return [title for _, title in titles[:SERIES_CONTEXT_LIMIT]]


async def generate_metadata_content(db, render_job_id: str) -> VideoMetadataFields:
    render_job_doc = await db["render_jobs"].find_one({"_id": render_job_id})
    if render_job_doc is None:
        raise ValueError(f"no render_jobs document for {render_job_id!r}")

    script = await db["scripts"].find_one({"_id": render_job_doc["script_id"]})
    if script is None:
        raise ValueError(f"no scripts document for {render_job_doc['script_id']!r}")

    prior_titles = await fetch_series_context(db, script["_id"])
    unit_id = render_job_doc["unit_id"]
    subtitle_target = max(YOUTUBE_TITLE_GUIDELINE_LENGTH - len(unit_id) - len(TITLE_SEPARATOR), 0)

    system = (
        "You write concise, accurate YouTube metadata for episodes of a devotional "
        "narration series. The episode's main title is already decided and fixed — "
        "you do not write it. Instead, write a short subtitle that will be appended "
        "after the fixed title as \"Main Title | Your Subtitle\". The subtitle is a single, "
        "complete, short sentence (not a list of themes, not a second question) adding "
        "specificity about this particular episode's content — a concrete theme, "
        "structure, or takeaway — and it must not repeat the fixed title's wording. "
        "Descriptions summarize the episode's content in 2-4 sentences. Tags are short, "
        "relevant keywords."
    )
    prompt_parts = [
        f"The episode's fixed title is: {unit_id!r}",
        f"Aim to keep your subtitle around {subtitle_target} characters or fewer so the "
        "combined title stays close to YouTube's typical length — but this is a soft "
        "target, not a hard limit: never sacrifice a complete, natural sentence just to "
        "hit it. Nothing will cut your subtitle short.",
        f"Episode script ({script['lang']}):\n{script['text']}",
    ]
    if prior_titles:
        prior_list = "\n".join(f"- {t}" for t in prior_titles)
        prompt_parts.append(f"Prior episode titles in this series (chronological, most recent first):\n{prior_list}")
    prompt_parts.append("Generate a subtitle, description, and tags for this episode.")
    prompt = "\n\n".join(prompt_parts)

    result = await generate_structured(system=system, prompt=prompt, schema=VideoMetadataSchema)
    assert isinstance(result, VideoMetadataSchema)
    return VideoMetadataFields(
        title=_compose_title(unit_id, result.subtitle),
        description=result.description,
        tags=result.tags,
    )
