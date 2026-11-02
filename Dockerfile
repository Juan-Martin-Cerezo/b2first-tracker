FROM python:3.13-slim
WORKDIR /app
COPY *.py ./
COPY index.html landing.html robots.txt sitemap.xml ./
COPY material/ ./material/
COPY assets/ ./assets/
COPY img/ ./img/
COPY docs/ ./docs/
ENV PORT=8088 \
    B2_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1
EXPOSE 8088
VOLUME ["/app/data"]
CMD ["python3", "server.py"]
