FROM python:3.12-slim

ENV VIP_PRICE_STARS=100 \
    LOG_LEVEL=INFO \
    DATA_FILE=/app/data/vip_data.json

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

VOLUME ["/app/data"]

CMD ["python", "bot.py"]
