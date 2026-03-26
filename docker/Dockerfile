FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    titiler.core==0.16.0 \
    uvicorn==0.27.1 \
    fastapi==0.110.0

COPY titiler/main.py .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
