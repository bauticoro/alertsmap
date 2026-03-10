#!/bin/bash
# Wrapper que ejecuta run_cycle.sh con intervalos aleatorios según el horario.
# El cron llama cada minuto; este script decide si ya pasó suficiente tiempo
# desde la última ejecución (intervalo random según período del día).

cd "$(dirname "$0")/.." || exit 1
export PATH="/usr/local/bin:/usr/bin:$PATH"

SCRIPT_DIR="$(pwd)"
RUN_SCRIPT="${RUN_CMD:-$SCRIPT_DIR/scripts/run_cycle.sh}"
LAST_RUN_FILE="${LAST_RUN_FILE:-$SCRIPT_DIR/.last_run_aliado}"

# Cargar .env si existe
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

# Hora actual (respeta TZ del cron, ej. America/Mexico_City)
HOUR=$(date +%H)

# Determinar período y rango de intervalo (min-max en segundos)
# Laboral 9-18: 4-8 min
# Transición 7-8, 19-22: 12-18 min
# Madrugada 0-6, 22-23: 25-35 min
if [ "$HOUR" -ge 9 ] && [ "$HOUR" -le 18 ]; then
  MIN_SEC=240   # 4 min
  MAX_SEC=480   # 8 min
elif ([ "$HOUR" -ge 7 ] && [ "$HOUR" -le 8 ]) || ([ "$HOUR" -ge 19 ] && [ "$HOUR" -le 22 ]); then
  MIN_SEC=720   # 12 min
  MAX_SEC=1080  # 18 min
else
  MIN_SEC=1500  # 25 min
  MAX_SEC=2100  # 35 min
fi

# Intervalo aleatorio en segundos
RANDOM_INTERVAL=$((MIN_SEC + RANDOM % (MAX_SEC - MIN_SEC + 1)))

NOW=$(date +%s)
LAST_RUN=0
[ -f "$LAST_RUN_FILE" ] && LAST_RUN=$(cat "$LAST_RUN_FILE")
ELAPSED=$((NOW - LAST_RUN))

if [ "$ELAPSED" -lt "$RANDOM_INTERVAL" ]; then
  # Aún no ha pasado suficiente tiempo, salir sin hacer nada
  exit 0
fi

# Ejecutar y guardar timestamp
if [ -n "$RUN_CMD" ]; then
  eval "$RUN_CMD"
else
  "$RUN_SCRIPT"
fi
echo "$NOW" > "$LAST_RUN_FILE"
