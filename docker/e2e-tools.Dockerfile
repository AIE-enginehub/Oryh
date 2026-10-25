# Test tooling for scripts/run_docker_e2e.sh: Python 3.13 with uv, plus the
# git and jq that some tests shell out to. Never deployed; the repository is
# copied in at run time, so this image holds no project code.
ARG ORYH_E2E_TOOLS_BASE=ghcr.io/astral-sh/uv:python3.13-bookworm-slim
FROM ${ORYH_E2E_TOOLS_BASE}

RUN apt-get update \
    && apt-get install -y --no-install-recommends git jq \
    && rm -rf /var/lib/apt/lists/*

# the image's own interpreter, never a downloaded one: the project pins
# >=3.13 and psycopg-binary has no wheel for newer CPython yet
ENV UV_PYTHON=/usr/local/bin/python3.13 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1
