# Smart Shopping application image (API, worker and controller roles are chosen by the container arguments).
# BASE_IMAGE is an argument so that the image can be built from an internal mirror too.
ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/src
WORKDIR /app

COPY requirements.txt ./
# only the runtime libraries: the test framework is not needed in the image
RUN grep -v '^pytest' requirements.txt > runtime-requirements.txt \
 && python -m pip install --no-cache-dir -r runtime-requirements.txt \
 && rm runtime-requirements.txt

COPY src ./src

# non-root user; the application writes nothing to disk (state lives in PostgreSQL)
RUN useradd --system --uid 10001 --no-create-home shopping
USER 10001

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8080/health/live', timeout=2)" || exit 1

ENTRYPOINT ["python", "-m", "shopping"]
CMD ["--role", "all", "--host", "0.0.0.0", "--port", "8080"]
