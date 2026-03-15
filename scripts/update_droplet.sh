#!/bin/bash
# Actualiza el código del Scraper de Aliado en el droplet de Digital Ocean.
# Ejecutar desde el directorio del proyecto: ./scripts/update_droplet.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

echo "🔄 Actualizando Scraper de Aliado en $(pwd)..."

# Pull del código
git fetch origin
git pull origin main

# Asegurar permisos de ejecución en scripts (git puede perderlos)
chmod +x scripts/run_cycle_random.sh scripts/run_cycle.sh scripts/setup_cron.sh

# Actualizar dependencias Python
if [ -f venv/bin/pip ]; then
  echo "📦 Actualizando dependencias Python..."
  venv/bin/pip install -q -r requirements.txt
fi

# Si usa Docker, reconstruir imagen
if command -v docker &>/dev/null && [ -f Dockerfile ]; then
  echo "🐳 Reconstruyendo imagen Docker..."
  docker build -t scraper-aliado .
fi

# Reiniciar servicio systemd si existe
if systemctl is-active --quiet aliado-monitor 2>/dev/null; then
  echo "🔄 Reiniciando aliado-monitor..."
  systemctl restart aliado-monitor
  echo "✅ Servicio reiniciado"
fi

echo "✅ Actualización completada. El cron usará el nuevo código en la próxima ejecución."
