# Optional NAIP service (TensorFlow). Kept apart from the backend (PyTorch) on purpose.
# Started only with:  make naip   (dev)   or   make prod-naip
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 TF_CPP_MIN_LOG_LEVEL=2

RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*

# TF 2.15 = last release with Keras 2 (the .h5 weights of the subclassed model need it)
RUN pip install --no-cache-dir \
        tensorflow-cpu==2.15.1 "numpy<2" \
        rasterio pyproj scikit-image pyyaml Pillow \
        pystac-client planetary-computer \
        fastapi==0.111.0 "uvicorn[standard]==0.29.0"

WORKDIR /app
COPY . .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
