FROM python:3.13-slim
WORKDIR /app
COPY server.py store.py prompts.py index.html ./
COPY material/ ./material/
COPY assets/ ./assets/
ENV PORT=8088 PYTHONUNBUFFERED=1
EXPOSE 8088
CMD ["python3", "server.py"]
