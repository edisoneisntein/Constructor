FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SIREP_DATABASE_PATH=/data/sirep.sqlite3 \
    SIREP_STORAGE_ROOT=/data/storage

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Puente TS/JS: sin @babel/parser el análisis profundo se degrada a inventario
# (files_analyzed=0). Se instala dentro de la imagen para que sobreviva rebuilds.
RUN npm install --prefix /app/bridges --no-save --no-package-lock @babel/parser

RUN mkdir -p /data/storage

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
