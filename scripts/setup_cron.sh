#!/bin/bash
# Configura cron para ejecutar el monitor con horario "natural" e intervalos aleatorios:
# - Horario laboral (9-18h): cada 4-8 min (random)
# - Mañana temprano / tarde-noche (7-9h, 19-22h): cada 12-18 min (random)
# - Madrugada (22h-7h): cada 25-35 min (random)
# El cron corre cada minuto; el wrapper decide si ejecutar según el intervalo aleatorio.
# Ejecutar desde el directorio del proyecto: ./scripts/setup_cron.sh

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_SCRIPT="$SCRIPT_DIR/scripts/run_cycle_random.sh"
LOG_FILE="${LOG_FILE:-$SCRIPT_DIR/aliado_scraper.log}"
CMD="cd $SCRIPT_DIR && $RUN_SCRIPT >> $LOG_FILE 2>&1"

# Hacer ejecutables
chmod +x "$RUN_SCRIPT"
chmod +x "$SCRIPT_DIR/scripts/run_cycle.sh"

# Cron cada minuto (el wrapper filtra con intervalos aleatorios)
CRON_LINE="* * * * * $CMD"

# Zona horaria (CDMX - ajustar si aplica)
TZ_LINE="${TZ:-America/Mexico_City}"

# Limpiar entradas anteriores y añadir las nuevas
{
  crontab -l 2>/dev/null | grep -v "run_cycle" | grep -v "aliado" | grep -v "^TZ="
  echo "TZ=$TZ_LINE"
  echo "# Scraper Aliado - horario natural + intervalos aleatorios"
  echo "$CRON_LINE"
} | crontab -

echo "✅ Cron configurado con horario natural e intervalos aleatorios:"
echo "   • 9:00-18:00 (laboral): cada 4-8 min (random)"
echo "   • 7:00-9:00 y 19:00-22:00: cada 12-18 min (random)"
echo "   • 22:00-7:00 (madrugada): cada 25-35 min (random)"
echo ""
echo "   Wrapper: $RUN_SCRIPT"
echo "   Log: $LOG_FILE"
echo ""
echo "Para ver el log: tail -f $LOG_FILE"
echo "Zona horaria: $TZ_LINE (cambiar con TZ=America/Santiago ./scripts/setup_cron.sh)"
