# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY requirements.lock.txt ./
COPY src ./src
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi \
    && pip install --no-cache-dir -c requirements.lock.txt .
COPY alembic.ini ./
COPY alembic ./alembic
COPY data ./data
RUN mkdir -p local_data
CMD ["python", "-m", "jobintel.runtime", "--host", "0.0.0.0"]
