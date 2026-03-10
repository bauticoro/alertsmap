#!/bin/bash
# Configura cron para ejecutar el monitor cada 5 minutos
# Ejecutar desde el directorio del proyecto: ./scripts/setup_cron.sh

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_SCRIPT="$SCRIPT_DIR/scripts/run_cycle.sh"
LOG_FILE="${LOG_FILE:-$SCRIPT_DIR/aliado_scraper.log}"
CRON_LINE="*/5 * * * * cd $SCRIPT_DIR && $RUN_SCRIPT >> $LOG_FILE 2>&1"

# Hacer ejecutable run_cycle.sh
chmod +x "$RUN_SCRIPT"

# Añadir al crontab del usuario actual (o root si prefieres)
(crontab -l 2>/dev/null | grep -v "run_cycle.sh" | grep -v "aliado"; echo "$CRON_LINE") | crontab -

echo "✅ Cron configurado: cada 5 minutos"
echo "   Script: $RUN_SCRIPT"
echo "   Log: $LOG_FILE"
echo ""
echo "Para ver el log: tail -f $LOG_FILE"
