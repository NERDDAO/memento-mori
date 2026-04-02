FROM python:3.12-slim

WORKDIR /app

# Install both engine and gateway (gateway imports engine code)
COPY engine/ engine/
COPY gateway/ gateway/
COPY defs/ defs/

RUN pip install --no-cache-dir -e engine/ -e gateway/

EXPOSE 8080

CMD ["uvicorn", "gateway.app:app", "--host", "0.0.0.0", "--port", "8080"]
