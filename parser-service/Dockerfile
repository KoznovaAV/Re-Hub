FROM python:3.12-slim
WORKDIR /app
COPY parser-service/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY parser-service/app ./app
COPY contracts/parser-result.schema.json ./contracts/parser-result.schema.json
USER 65534:65534
EXPOSE 8001
CMD ["python", "-u", "app/main.py"]
