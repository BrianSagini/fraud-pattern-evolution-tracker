FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY dashboard/ ./dashboard/
ENV PYTHONPATH=/app

EXPOSE 8501
