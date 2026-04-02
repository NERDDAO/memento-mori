FROM python:3.12-slim

WORKDIR /app

COPY engine/ engine/
COPY defs/ defs/

RUN pip install --no-cache-dir -e engine/

CMD ["python", "-m", "memento.matrix_listener"]
