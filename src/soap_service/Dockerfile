FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app
COPY src/soap_service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY src/common /app/src/common
COPY src/soap_service /app/src/soap_service
EXPOSE 8001
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:8001 --workers ${SOAP_WORKERS:-4} --timeout ${SOAP_TIMEOUT:-120} src.soap_service.wsgi:application"]
