FROM python:3.12-slim

WORKDIR /app

# Non-root user for production security
RUN addgroup --system app && adduser --system --ingroup app --no-create-home app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chown -R app:app /app

USER app

EXPOSE 8000

# WEB_CONCURRENCY defaults to 2; LOG_LEVEL defaults to warning
# Override via env var: -e WEB_CONCURRENCY=4
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-2} --log-level ${LOG_LEVEL:-warning}"]
