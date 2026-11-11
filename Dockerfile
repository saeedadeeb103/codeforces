FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
RUN useradd --create-home appuser
USER appuser

ENV PORT=8000
EXPOSE 8000
# Railway injects $PORT. Forwarded headers are NOT trusted wholesale (they can be spoofed);
# redirects are relative, and the login throttle reads the client IP from X-Real-IP (see config).
CMD ["sh", "-c", "exec uvicorn --factory app.main:create_app --host 0.0.0.0 --port ${PORT} --no-proxy-headers"]
