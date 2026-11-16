FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Istanbul \
    VIDEO_OUTPUT_ROOT=/data

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /tmp/video-requirements.txt
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then \
      PIP_CERT=/run/secrets/build_ca pip install --no-cache-dir -r /tmp/video-requirements.txt; \
    else \
      pip install --no-cache-dir -r /tmp/video-requirements.txt; \
    fi
COPY . /app/automation/
RUN useradd --create-home --uid 1000 mbsvideo \
    && mkdir -p /data /private \
    && chown -R mbsvideo:mbsvideo /app /data /private \
    && chmod -R u+rwX,go+rX /app/automation
USER mbsvideo

ENTRYPOINT ["python", "-m", "automation.worker"]
