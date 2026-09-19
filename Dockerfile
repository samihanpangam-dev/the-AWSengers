# ── Omni-File AI Agent — Production Dockerfile ────────────────────────────────
#
# Build:   docker build -t omni-agent .
# Run dev: docker run --rm -e ENV=development -p 8000:8000 omni-agent
# Run prod: docker run --rm \
#             -e ENV=production \
#             -e BEDROCK_MODEL_ID=us.amazon.nova-pro-v1:0 \
#             -e BEDROCK_GUARDRAIL_ID=<your-id> \
#             -e AWS_REGION=us-east-1 \
#             -e AWS_ACCESS_KEY_ID=<key> \
#             -e AWS_SECRET_ACCESS_KEY=<secret> \
#             -p 8000:8000 omni-agent
#
# Why python:3.12-slim and not alpine?
#   PyMuPDF and ffmpeg-python ship pre-built wheels for Debian (glibc).
#   Alpine uses musl libc and forces a slow from-source compile that often
#   fails. slim gives us the smallest Debian-based image (~45 MB base).
# ──────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

# ── System dependencies ───────────────────────────────────────────────────────
# ffmpeg  — required by ffmpeg-python for all audio/video synthesis scripts.
# --no-install-recommends keeps the layer as small as possible.
# The rm -rf at the end discards the apt cache so it does not bloat the image.

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# ── Working directory ─────────────────────────────────────────────────────────

WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────────────
# Copy requirements before source so Docker can cache this layer independently.
# A source-only change will skip the (slow) pip install on rebuild.

COPY backend/requirements.txt ./backend/requirements.txt

RUN pip install --no-cache-dir -r backend/requirements.txt

# ── Application source ────────────────────────────────────────────────────────

COPY backend/ ./backend/

# ── Runtime configuration ─────────────────────────────────────────────────────
# ENV=production is the safe default for a container image.
# Override at `docker run` time with -e ENV=development for local testing.
# UPLOAD_TMP_DIR uses the container's ephemeral /tmp — wiped on container stop.

ENV ENV=production
ENV UPLOAD_TMP_DIR=/tmp/omni_agent
ENV BEDROCK_MODEL_ID=us.amazon.nova-pro-v1:0
ENV AWS_REGION=us-east-1

# ── Network ───────────────────────────────────────────────────────────────────

EXPOSE 8000

# ── Entrypoint ────────────────────────────────────────────────────────────────
# Single worker is correct for App Runner (it manages horizontal scaling).
# Increase --workers only if self-hosting behind a load balancer.

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
