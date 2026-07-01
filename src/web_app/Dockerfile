FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app
COPY src/web_app/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY src/common /app/src/common
COPY src/web_app /app/src/web_app
EXPOSE 5051
CMD ["uvicorn", "src.web_app.main:app", "--host", "0.0.0.0", "--port", "5051"]
