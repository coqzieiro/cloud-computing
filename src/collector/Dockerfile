FROM python:3.11-slim

WORKDIR /app
COPY src/collector/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY src/collector /app/src/collector
EXPOSE 8080
CMD ["python", "-m", "src.collector.collector"]
