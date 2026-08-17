ARG ORYH_API_BASE=python:3.13-slim
FROM ${ORYH_API_BASE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
COPY skills ./skills

# The Yunxiao release pipeline injects an ACR-hosted dependency image which
# already contains /app/.venv. Keep the official Python image as a portable
# fallback for local builds.
RUN if [ ! -d /app/.venv ]; then \
      pip install --upgrade pip \
      && pip install .; \
    fi

EXPOSE 8000

CMD ["sh", "-c", "python scripts/bootstrap_db_roles.py && alembic upgrade head && python scripts/sync_tenant_defaults.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
