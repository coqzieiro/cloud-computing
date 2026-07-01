FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app
COPY src/rest_service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY src/common /app/src/common
COPY src/rest_service /app/src/rest_service
EXPOSE 8000
CMD ["sh", "-c", "uvicorn src.rest_service.main:app --host 0.0.0.0 --port 8000 --workers ${REST_WORKERS:-4} --timeout-keep-alive ${REST_KEEPALIVE_TIMEOUT:-15}"]
