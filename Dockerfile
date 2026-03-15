FROM mambaorg/micromamba:1.5.10

WORKDIR /app

COPY --chown=mambauser:mambauser . /app

RUN micromamba create -y -n plantvirome -f envs/plantvirome.yml && \
    micromamba clean --all --yes

USER root
RUN mkdir -p /data && chown -R mambauser:mambauser /app /data
USER mambauser

ENV PYTHONUNBUFFERED=1
ENV PVP_RUNTIME_DIR=/data
ENV PVP_ALLOW_REAL_RUNS=false
ENV PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD micromamba run -n plantvirome python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT', '8000'), timeout=5)"

CMD ["sh", "-c", "micromamba run -n plantvirome python -m plant_virus_pipeline serve --host 0.0.0.0 --port ${PORT:-8000}"]
