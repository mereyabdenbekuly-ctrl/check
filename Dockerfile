FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VERIDROP_JOBS_DIR=/data/jobs \
    VERIDROP_WISHLIST_PATH=/data/wishlist.txt

RUN apt-get update && apt-get install -y --no-install-recommends \
      fonts-dejavu-core \
      fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY web ./web
COPY data ./data

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[web]" \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && mkdir -p /data/jobs/anthropic /data/jobs/openai /data/jobs/gemini \
    && chown -R appuser:appuser /app /data

USER appuser

EXPOSE 8088

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8088/healthz', timeout=3)" || exit 1

CMD ["uvicorn", "web.server:app", "--host", "0.0.0.0", "--port", "8088", "--proxy-headers", "--forwarded-allow-ips=*"]
