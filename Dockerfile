# The application image.
#
# Deliberately runs waitress as a SINGLE process with threads, the same way it
# runs on the office machine. The restore lock (config.RESTORE_IN_PROGRESS) is
# a variable in memory: with several worker processes only one of them would
# know a restore is running and the others would keep serving and writing.
# Threads share that memory; separate processes do not.

FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# postgresql-client for the deploy-time database restore, curl for the
# container health check
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client curl \
    && rm -rf /var/lib/apt/lists/*

# dependencies first so a code change does not reinstall them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# run as a normal user: a web process has no business being root
RUN useradd --create-home --uid 10001 warehouse \
    && mkdir -p /app/logs /app/backups /app/uploads \
    && chown -R warehouse:warehouse /app \
    && chmod +x /app/docker-entrypoint.sh
USER warehouse

EXPOSE 5000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["python", "wsgi.py"]
