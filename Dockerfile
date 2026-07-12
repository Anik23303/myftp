FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ftp_server.py .
COPY api_server.py .

EXPOSE 21 5000

CMD ["sh", "-c", "python api_server.py & python ftp_server.py"]
