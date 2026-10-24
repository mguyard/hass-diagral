FROM python:3.14-slim

RUN pip install --no-cache-dir aiohttp==3.14.5

COPY server.py /app/server.py

ENV PYTHONUNBUFFERED=1
EXPOSE 8099
CMD ["python", "/app/server.py"]
