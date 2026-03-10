# Despliegue en Digital Ocean

Guía para ejecutar el Scraper de Aliado en un droplet de Digital Ocean, con ejecución cada 5 minutos.

## Opción 1: Droplet con cron (recomendado)

### 1. Crear el droplet

- **Imagen**: Ubuntu 22.04 LTS
- **Plan**: Basic $4/mes (1 GB RAM) es suficiente
- **Región**: La más cercana a ti

### 2. Conectarte por SSH

```bash
ssh root@TU_IP_DEL_DROPLET
```

### 3. Instalar dependencias

```bash
apt update && apt install -y python3 python3-pip python3-venv git
```

### 4. Clonar el proyecto

```bash
cd /opt
git clone https://github.com/bauticoro/alertsmap.git scraper-aliado
cd scraper-aliado
```

*(Si el repo es privado, configura SSH keys o un token.)*

Si vas a usar `GITHUB_TOKEN` para que el droplet suba las alertas automáticamente, configura git para los commits:

```bash
git config user.email "tu-email@ejemplo.com"
git config user.name "Tu Nombre"
```

### 5. Crear entorno virtual e instalar dependencias

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 6. Configurar variables de entorno

```bash
cp .env.example .env
nano .env
```

Edita `.env` con tus valores:

```
WHAPI_TOKEN=tu_token_de_whapi
WHAPI_GROUP_ID=120363423858096188@g.us

# Opcional: para que el droplet suba web/alertas.json a GitHub (la página se actualizará)
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**GITHUB_TOKEN** (opcional): Si lo configuras, cada vez que el scraper termine, el droplet hará `git push` de `web/alertas.json` a tu repo. Así Vercel/GitHub Pages desplegará automáticamente y la página del mapa siempre mostrará las alertas más recientes. Crear el token en: GitHub → Settings → Developer settings → Personal access tokens (permiso `repo`).

### 7. Configurar cron (horario natural + intervalos aleatorios)

El script configura un cron que trabaja más en horario laboral, descansa de noche, y usa **intervalos aleatorios** para parecer más natural:

| Horario | Intervalo (random) |
|---------|---------------------|
| 9:00–18:00 (laboral) | 4–8 min |
| 7:00–9:00 y 19:00–22:00 | 12–18 min |
| 22:00–7:00 (madrugada) | 25–35 min |

El cron corre cada minuto; un wrapper decide si ejecutar según el intervalo aleatorio del período.

```bash
chmod +x scripts/run_cycle.sh
chmod +x scripts/run_cycle_random.sh
chmod +x scripts/setup_cron.sh
./scripts/setup_cron.sh
```

El log se guarda en `aliado_scraper.log` dentro del proyecto. Para usar `/var/log`:

```bash
LOG_FILE=/var/log/aliado_scraper.log ./scripts/setup_cron.sh
```

Para otra zona horaria (por defecto CDMX):

```bash
TZ=America/Santiago LOG_FILE=/var/log/aliado_scraper.log ./scripts/setup_cron.sh
```

O manualmente con `crontab -e`:

```
TZ=America/Mexico_City
* * * * * cd /opt/scraper-aliado && ./scripts/run_cycle_random.sh >> /opt/scraper-aliado/aliado_scraper.log 2>&1
```

### 8. Probar manualmente

```bash
cd /opt/scraper-aliado
source venv/bin/activate
python monitor_alertas.py --once
```

---

## Opción 2: Docker en el droplet

Si prefieres usar contenedores:

### 1. Instalar Docker en el droplet

```bash
apt update && apt install -y docker.io
```

### 2. Construir y ejecutar

```bash
cd /opt/scraper-aliado
docker build -t scraper-aliado .
```

Para ejecutar con cron (horario natural + intervalos aleatorios, ver tabla arriba):

**Con venv en el host:**
```
TZ=America/Mexico_City
* * * * * cd /opt/scraper-aliado && ./scripts/run_cycle_random.sh >> /var/log/aliado.log 2>&1
```

**Solo Docker** (sin venv en el host, reemplaza `RUN_CMD`):
```
TZ=America/Mexico_City
* * * * * cd /opt/scraper-aliado && RUN_CMD='docker run --rm -e WHAPI_TOKEN=xxx -e WHAPI_GROUP_ID=xxx -v /opt/scraper-aliado/output:/app/output scraper-aliado python monitor_alertas.py --once' ./scripts/run_cycle_random.sh >> /var/log/aliado.log 2>&1
```

*(Nota: el volumen `output` persiste los JSON y `sent_alert_ids.json` entre ejecuciones.)*

---

## Opción 3: Monitor en bucle (sin cron)

Si prefieres un proceso que corre continuamente y hace un ciclo cada 5 minutos:

```bash
cd /opt/scraper-aliado
source venv/bin/activate
nohup python monitor_alertas.py &
```

O con systemd para que se reinicie si falla:

```bash
# Crear /etc/systemd/system/aliado-monitor.service
[Unit]
Description=Monitor de alertas Aliado
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/scraper-aliado
ExecStart=/opt/scraper-aliado/venv/bin/python monitor_alertas.py
Restart=always
RestartSec=60
EnvironmentFile=/opt/scraper-aliado/.env

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable aliado-monitor
systemctl start aliado-monitor
systemctl status aliado-monitor
```

---

## Actualizar el código en el droplet

Cuando hagas cambios y los subas a GitHub, actualiza el droplet así:

### 1. Desde tu máquina local: commit y push

```bash
git add .
git commit -m "Descripción de los cambios"
git push origin main
```

### 2. En el droplet: ejecutar el script de actualización

```bash
ssh root@TU_IP_DEL_DROPLET
cd /opt/scraper-aliado
chmod +x scripts/update_droplet.sh
./scripts/update_droplet.sh
```

El script hace `git pull`, actualiza dependencias, reconstruye Docker (si lo usas) y reinicia el servicio systemd (si existe). Si usas cron, no hace falta reiniciar nada: el cron usará el nuevo código en la próxima ejecución.

---

## Ver logs

```bash
tail -f /var/log/aliado_scraper.log
```

## Comandos útiles

| Acción | Comando |
|--------|---------|
| Ver crontab | `crontab -l` |
| Editar crontab | `crontab -e` |
| Probar un ciclo manual | `python monitor_alertas.py --once` |
| Ver estado systemd | `systemctl status aliado-monitor` |
