# Ollama with the demonstration models baked into the image, so that the cluster needs no internet access at run time
# and a pod that is evicted and restarted on the other node pool is ready within seconds.
# Build (needs internet, downloads the weights once):  docker build -t shopping-ollama:dev deploy/ollama
ARG OLLAMA_IMAGE=ollama/ollama:0.9.6
FROM ${OLLAMA_IMAGE}
# GREEN uses the first model, AMBER the second (SHOPPING_LOCAL_MODEL, SHOPPING_LOCAL_MODEL_AMBER)
ARG MODELS="qwen2.5:1.5b qwen2.5:0.5b"
RUN ollama serve & pid=$!; \
    for i in $(seq 1 60); do ollama list >/dev/null 2>&1 && break; sleep 1; done; \
    for m in $MODELS; do ollama pull "$m" || exit 1; done; \
    kill $pid; wait $pid || true
