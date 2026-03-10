# Scraper de Aliado - Imagen para Digital Ocean
FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema para Pillow/staticmaps (gráficos)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scrape_aliado_mexico.py .
COPY mapa_alertas.py .
COPY monitor_alertas.py .
COPY send_whatsapp.py .

RUN mkdir -p output

# Variables de entorno requeridas en runtime:
# WHAPI_TOKEN, WHAPI_GROUP_ID
ENV PYTHONUNBUFFERED=1

CMD ["python", "monitor_alertas.py"]
