FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y git curl nano sqlite3 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/. app/
COPY run.py .

#CMD ["python", "run.py"]