FROM python:3.11-slim

WORKDIR /app

# Set PYTHONPATH
ENV PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "bot.main"]

