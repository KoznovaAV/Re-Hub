FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
USER 65534:65534
EXPOSE 8001
CMD ["python", "-u", "app/main.py"]
