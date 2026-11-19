FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY requirements-import.txt ./
RUN python -m pip install --no-cache-dir -r requirements-import.txt
COPY app/ ./
USER 65534:65534
EXPOSE 8001
CMD ["python", "-u", "main.py"]
