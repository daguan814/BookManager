FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

EXPOSE 18080

CMD ["sh", "-c", "if [ -n \"$SSL_CERT_FILE\" ] && [ -n \"$SSL_KEY_FILE\" ] && [ -f \"$SSL_CERT_FILE\" ] && [ -f \"$SSL_KEY_FILE\" ]; then exec gunicorn -w ${GUNICORN_WORKERS:-2} -k gthread --threads ${GUNICORN_THREADS:-4} -b ${APP_HOST:-0.0.0.0}:${APP_PORT:-18080} --certfile \"$SSL_CERT_FILE\" --keyfile \"$SSL_KEY_FILE\" main:app; else exec gunicorn -w ${GUNICORN_WORKERS:-2} -k gthread --threads ${GUNICORN_THREADS:-4} -b ${APP_HOST:-0.0.0.0}:${APP_PORT:-18080} main:app; fi"]
