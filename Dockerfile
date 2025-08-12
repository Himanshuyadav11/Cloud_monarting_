FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \ PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requrirements.txt .

RUN python -m venv /opt.venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requrirements.txt \
    && /opt/venv/bin/pip install gunicorn

#MULTI STAGE BUILD
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN useradd -m appuser

COPY --from=builder /opt/venv /opt/venv

COPY . .

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app", "--workers", "4", "--timeout", "120"]
