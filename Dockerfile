FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PVP_RUNTIME_DIR=/data
ENV PVP_ALLOW_REAL_RUNS=false
ENV PORT=8000

COPY . /app

RUN python -m pip install --upgrade pip && \
    python -m pip install .

RUN mkdir -p /data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT', '8000'), timeout=5)"

CMD ["sh", "-c", "python -m plant_virus_pipeline serve --host 0.0.0.0 --port ${PORT:-8000}"]
