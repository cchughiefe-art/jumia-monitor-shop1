FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/app/data
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home bot
COPY main.py healthcheck.py bot.py telegram_bot.py telegram_api.py jumia_client.py ./
RUN mkdir /app/data && chown -R bot:bot /app
USER bot
VOLUME /app/data
CMD ["python", "main.py"]
