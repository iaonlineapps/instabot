FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY bot/ ./bot/
VOLUME /data
EXPOSE 8097
CMD ["python", "-u", "bot/main.py"]
