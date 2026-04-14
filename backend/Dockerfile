FROM python:3.9-slim

WORKDIR /app

# System libraries needed to compile MinkowskiEngine
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install numpy first — MinkowskiEngine setup.py imports it at metadata time
RUN pip install --no-cache-dir numpy==1.26.4

# Install PyTorch (CPU-only) — MinkowskiEngine also needs it at compile time
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    torch==2.3.0+cpu

# Install MinkowskiEngine (CPU-only, no CUDA)
# Python 3.9 has intact distutils and collections ABC aliases — no patches needed
RUN FORCE_CUDA=0 pip install --no-cache-dir MinkowskiEngine

# Install the rest of the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
