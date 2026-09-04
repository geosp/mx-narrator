FROM python:3.11-slim

# ffmpeg (assembly/concat) and espeak-ng (phonemization for some engines) — mx_narrator's
# own README.md documents these as system packages not installed by uv. git is needed
# because chatterbox-tts and ctc-forced-aligner are pinned to a specific commit via a
# git source, not PyPI. build-essential (gcc/g++) is needed because ctc-forced-aligner's
# git-sourced build compiles a native extension during `uv sync` below — confirmed the
# hard way (RuntimeError: Unsupported compiler) without it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg espeak-ng git build-essential \
    && rm -rf /var/lib/apt/lists/*

# Pinned to match this project's own uv.lock format version (uv 0.9.4, per pyproject.toml's
# build-system requirement) rather than floating on `latest`.
COPY --from=ghcr.io/astral-sh/uv:0.9.4 /uv /uvx /bin/

WORKDIR /app

# Copy only what `uv sync --frozen` needs to resolve/build, then the package source.
# mx_narrator's pyproject.toml declares `readme = "README.md"`, so uv_build needs it present.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# --no-cache keeps the image from retaining uv's download cache; --frozen refuses to
# touch uv.lock, so a drifted lockfile fails the build loudly instead of silently
# resolving something different than the host used.
RUN uv sync --frozen --no-cache

# ctranslate2 (faster-whisper's backend) doesn't self-locate its pip-installed CUDA
# libs the way torch does (torch bakes absolute RPATHs into its own wheel) — it just
# dlopen()s by soname, so it needs these on the loader's search path explicitly.
# Confirmed necessary via a real host-side repro (RuntimeError: libcublas.so.12 is
# not found or cannot be loaded) before adding this.
ENV LD_LIBRARY_PATH="/app/.venv/lib/python3.11/site-packages/nvidia/cublas/lib:/app/.venv/lib/python3.11/site-packages/nvidia/cudnn/lib"

# fontconfig + fonts-dejavu-core: ffmpeg's `subtitles` filter (worker/video.py) burns
# captions in via libass, already pulled in as a dependency of the `ffmpeg` package
# itself — but --no-install-recommends means no font ships by default, and libass
# needs an actual font file to render text with. Deliberately a separate, later RUN
# step (not folded into the apt-get above) so adding a runtime-only package here
# doesn't invalidate the `uv sync` layer above it — that one reinstalls this
# project's entire ML dependency stack (torch, transformers, ctranslate2, ...) and
# is by far the most expensive layer in this image, confirmed the hard way.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fontconfig fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# The Temporal worker entrypoint and the FastAPI backend — imports mx_narrator as a
# dependency, doesn't modify it (proposal.md). This one image serves both the
# `gpu-worker` and `api` compose services (see docker-compose.yml's `api` service
# comment); copied after `uv sync` so editing app code doesn't invalidate the (much
# slower) dependency-install layer above.
COPY worker ./worker
COPY api ./api

CMD ["uv", "run", "python", "-m", "worker.main"]
