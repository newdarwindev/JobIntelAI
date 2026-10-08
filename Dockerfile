FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY requirements.lock.txt ./
COPY src ./src
RUN pip install --no-cache-dir -c requirements.lock.txt .
COPY alembic.ini ./
COPY alembic ./alembic
COPY data ./data
RUN mkdir -p local_data
CMD ["uvicorn", "jobintel.api:app", "--host", "0.0.0.0", "--port", "8000"]
