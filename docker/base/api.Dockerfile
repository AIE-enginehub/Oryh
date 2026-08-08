FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./

RUN uv sync --locked --no-dev --no-install-project
