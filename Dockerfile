FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY main.py integrations.py index.html ./
ENV N8N_WEBHOOK_BASE_URL=http://host.docker.internal:5679/webhook
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
