FROM python:3.11-slim

# Default PyPI torch wheel on Linux bundles CUDA support (nvidia-* deps) already —
# no special index needed, confirmed for this project's own mx-narrator CLI earlier.
RUN pip install --no-cache-dir --timeout 300 --retries 5 torch

COPY check_gpu.py /app/check_gpu.py

ENTRYPOINT ["python", "/app/check_gpu.py"]
