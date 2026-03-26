FROM python:3.11

WORKDIR /app

RUN pip install --no-cache-dir \
    titiler.core==0.16.0 \
    uvicorn==0.27.1 \
    fastapi==0.110.0 \
    rasterio==1.3.10

COPY titiler/main.py .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]