FROM python:3.12-slim
WORKDIR /app
COPY services/shared /app/shared
COPY services/scorer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY db /app/db
COPY services/scorer /app/scorer
ENV PYTHONPATH=/app
CMD ["uvicorn", "scorer.main:app", "--host", "0.0.0.0", "--port", "8002"]
