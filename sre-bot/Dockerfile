FROM python:3.12-slim
WORKDIR /bot
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn==23.0.0
COPY sre_bot ./sre_bot
RUN useradd --system bot && mkdir -p /data/tickets && chown bot /data/tickets
USER bot
EXPOSE 8000
CMD ["gunicorn", "-b", "0.0.0.0:8000", "-w", "1", "--threads", "4", "sre_bot.app:create_app()"]
