FROM python:3.12-slim
WORKDIR /app
COPY app/main.py ./
USER 65534:65534
EXPOSE 8001
CMD ["python", "-u", "main.py"]
