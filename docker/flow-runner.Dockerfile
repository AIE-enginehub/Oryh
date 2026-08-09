# The hosted flow runner: the dispatcher (Python) and the agent harness (pi,
# Node) in one image.
#
# They share an image because the dispatcher invokes pi as a subprocess, once
# per run. pi is a CLI harness rather than a service, so a separate pi container
# would need an HTTP shim in front of it — a hop, a protocol and a failure mode
# bought for nothing. The container is the resident part; the agent session is
# per run, which is what keeps one tenant's records out of another's context.
#
# It is still a separate image from the API on purpose: an agent runtime that
# hangs, leaks or gets an npm advisory must not be in the record layer's image,
# and the two scale on completely unrelated signals.

ARG ORYH_RUNNER_BASE=python:3.13-slim
FROM ${ORYH_RUNNER_BASE}

ARG PI_VERSION=0.83.0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # pi checks for updates and phones home on startup by default. A fleet
    # process should do neither: pin the version in the image and let the image
    # be the unit of change.
    PI_OFFLINE=1 \
    PI_SKIP_VERSION_CHECK=1 \
    PI_TELEMETRY=0

WORKDIR /app

# curl is how the skills reach the API — pi's built-in tools are file and shell
# operations, so the agent's REST calls all go through bash.
#
# Node comes from NodeSource, not Debian: pi requires >=22.19, and bookworm
# ships 20.x, on which pi's own dependencies fail to load at all
# (`webidl.util.markAsUncloneable is not a function`).
ARG NODE_MAJOR=22
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
       | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" \
       > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get purge -y gnupg && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Fail the build rather than the first run if the base image's Node drifts
# below what pi needs.
RUN node -e "const [maj,min]=process.versions.node.split('.').map(Number); if (maj<22 || (maj===22 && min<19)) { console.error('pi needs node >=22.19, got '+process.versions.node); process.exit(1); }"

RUN npm install -g "@earendil-works/pi-coding-agent@${PI_VERSION}" \
    && npm cache clean --force

COPY pyproject.toml README.md ./
COPY flow_runner ./flow_runner

# The runner is stdlib-only; this is here so the image fails loudly at build
# time if that ever stops being true. It runs BEFORE the agent's toolbox is
# installed, which is what makes it proof rather than decoration.
RUN python -c "import flow_runner.dispatcher, flow_runner.adapter, flow_runner.bundles"

# The AGENT's toolbox, not the runner's. pi drives the skills through shell and
# python, and a spreadsheet import means openpyxl. Without it an agent asked to
# read an .xlsx unzips the workbook and parses the XML by hand — which works on
# a simple sheet and quietly misreads merged headers, formulas and encodings,
# so the failure arrives as wrong data rather than an error.
#
# Deliberately not a `pyproject` dependency: the dispatcher must stay
# importable with nothing installed, and the check above proves it still is.
# The verification below builds a workbook with the awkward parts — two sheets,
# a merged banner, a formula, non-ASCII, a trailing total — and reads it back,
# so a fresh Pod cannot start without a toolchain that handles them.
COPY docker/verify-xlsx-toolchain.py /tmp/verify-xlsx-toolchain.py
RUN pip install --no-cache-dir "openpyxl==3.1.5" \
    && python /tmp/verify-xlsx-toolchain.py \
    && rm /tmp/verify-xlsx-toolchain.py

# Never root: the agent runs shell commands, and the blast radius of a prompt
# injection should not include the container's own filesystem.
# /var/lib/oryh-flow-runner holds the keys the runner issued itself, and is a
# named volume so a restart does not re-issue for every tenant. It is created
# and chowned HERE rather than only in compose: docker seeds a fresh named
# volume from the image's directory, so ownership set at build time is what the
# volume gets — otherwise it mounts root-owned and the runner, which is
# deliberately not root, cannot write its own state.
RUN useradd --create-home --uid 10001 runner \
    && mkdir -p /var/tmp/oryh-flow-runner /var/lib/oryh-flow-runner \
    && chown -R runner:runner /var/tmp/oryh-flow-runner /var/lib/oryh-flow-runner /app \
    && chmod 700 /var/lib/oryh-flow-runner
USER runner

ENV HOME=/home/runner

CMD ["python", "-m", "flow_runner"]
