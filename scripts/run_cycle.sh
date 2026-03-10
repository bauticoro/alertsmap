#!/bin/bash
# Ejecuta un ciclo del monitor (scraper + detectar nuevas + enviar WhatsApp)
# Para usar con cron: */5 * * * * /ruta/scripts/run_cycle.sh >> /var/log/aliado.log 2>&1

cd "$(dirname "$0")/.." || exit 1
export PATH="/usr/local/bin:/usr/bin:$PATH"

# Cargar .env si existe
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

# Usar venv si existe
if [ -f venv/bin/python ]; then
  exec venv/bin/python monitor_alertas.py --once
else
  exec python3 monitor_alertas.py --once
fi
