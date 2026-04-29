FROM python:3.12-slim
WORKDIR /app
COPY services/shared /app/shared
COPY services/summariser/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY db /app/db
COPY services/summariser /app/summariser
ENV PYTHONPATH=/app
CMD ["uvicorn", "summariser.main:app", "--host", "0.0.0.0", "--port", "8003"]
