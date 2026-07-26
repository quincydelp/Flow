FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLOW_DATA_DIR=/data

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY finance_demo ./finance_demo
RUN pip install --no-cache-dir ".[agents,yaml]"

COPY workflows ./workflows

EXPOSE 8000

CMD ["flow", "serve", "--host", "0.0.0.0", "--port", "8000", "--workflows", "workflows", "--import", "finance_demo.registrations"]
