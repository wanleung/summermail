FROM python:3.12-slim
WORKDIR /app
COPY services/shared /app/shared
COPY services/fetcher/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY db /app/db
COPY services/fetcher /app/fetcher
ENV PYTHONPATH=/app
CMD ["uvicorn", "fetcher.main:app", "--host", "0.0.0.0", "--port", "8001"]
