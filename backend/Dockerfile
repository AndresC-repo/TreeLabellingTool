# ── Stage 1: borrow the CUDA stubs from the devel image ──────────────────────
# libcuda.so.1 (stub) lets spconv's core_cc.so load at runtime without a
# physical GPU or GPU driver.  The stub satisfies the dynamic linker; since all
# inference runs on CPU tensors no actual CUDA calls are ever made.
FROM nvidia/cuda:11.8.0-devel-ubuntu22.04 AS cuda-stubs


# ── Stage 2: slim runtime ─────────────────────────────────────────────────────
FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# Python 3.11 + OpenMP (required by PyTorch CPU kernels)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3-pip \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.11 /usr/local/bin/python && \
    python -m pip install --upgrade pip

# Copy CUDA stub library from the devel image.
# With LD_LIBRARY_PATH pointing here, the dynamic linker finds libcuda.so.1
# when loading spconv.core_cc — no GPU hardware required.
COPY --from=cuda-stubs /usr/local/cuda/lib64/stubs /usr/local/cuda/lib64/stubs
ENV LD_LIBRARY_PATH=/usr/local/cuda/lib64/stubs:${LD_LIBRARY_PATH:-}

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir numpy==1.26.4

# CPU-only PyTorch — keeps image small; all tensors stay on CPU at inference time
RUN pip install --no-cache-dir torch==2.3.0+cpu \
    --extra-index-url https://download.pytorch.org/whl/cpu

# spconv-cu118: pre-built wheel — includes core_cc.so, no compilation needed.
# This is the only way to get core_cc.so without nvcc; building from source
# without CUDA silently skips all compilation and produces an empty extension.
RUN pip install --no-cache-dir spconv-cu118

# Verify the import works now (at build time), before we ever need a GPU.
RUN python -c "import spconv.pytorch; print('[OK] spconv imported successfully')"

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
