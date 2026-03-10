#!/usr/bin/env python3
"""
Monitor que ejecuta el scraper cada 5 minutos, detecta alertas nuevas
y las envía al grupo de WhatsApp con un mapa (pantallazo) cada una.
Si hay varias alertas nuevas, se envían en mensajes separados.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from send_whatsapp import send_single_alert

load_dotenv()

SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR / "output"
SENT_IDS_FILE = OUTPUT_DIR / "sent_alert_ids.json"
INTERVAL_SECONDS = 5 * 60  # 5 minutos


def load_sent_ids() -> set:
    """Carga los IDs de alertas ya enviadas."""
    if not SENT_IDS_FILE.exists():
        return set()
    try:
        with open(SENT_IDS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("ids", []))
    except (json.JSONDecodeError, OSError):
        return set()


def save_sent_ids(ids: set) -> None:
    """Guarda los IDs de alertas enviadas."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(SENT_IDS_FILE, "w", encoding="utf-8") as f:
        json.dump({"ids": list(ids)}, f, indent=2)


def run_scraper() -> bool:
    """Ejecuta el scraper de Aliado."""
    scraper = SCRIPT_DIR / "scrape_aliado_mexico.py"
    if not scraper.exists():
        print(f"❌ No se encontró {scraper}")
        return False
    result = subprocess.run(
        [sys.executable, str(scraper)],
        cwd=str(SCRIPT_DIR),
        capture_output=True,
        text=True,
        timeout=600,  # 10 min máximo
    )
    if result.returncode != 0:
        print(f"❌ Error en scraper: {result.stderr}")
        return False
    return True


def get_latest_alerts() -> list:
    """Obtiene las alertas del archivo JSON más reciente."""
    files = list(OUTPUT_DIR.glob("alertas_mexico_*.json"))
    if not files:
        return []
    latest = max(files, key=lambda p: p.stat().st_mtime)
    with open(latest, encoding="utf-8") as f:
        return json.load(f)


def run_cycle() -> int:
    """
    Ejecuta un ciclo: 1) scraper 2) detectar nuevas 3) enviar cada una.
    Retorna el número de alertas enviadas.
    """
    print("\n" + "=" * 60)
    print(f"🔄 Ciclo iniciado: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. Ejecutar scraper
    print("📡 Ejecutando scraper...")
    if not run_scraper():
        return 0
    print("✅ Scraper completado")

    # 2. Cargar alertas y detectar nuevas
    alertas = get_latest_alerts()
    if not alertas:
        print("   No hay alertas en el archivo más reciente")
        return 0

    sent_ids = load_sent_ids()

    # Primera ejecución: marcar todas como ya vistas sin enviar nada
    if not SENT_IDS_FILE.exists() and alertas:
        all_ids = {a["id"] for a in alertas if a.get("id")}
        save_sent_ids(all_ids)
        sent_ids = all_ids
        print(f"   📋 Inicio: {len(all_ids)} alertas existentes marcadas (sin enviar)")

    # Solo alertas nuevas Y con status ACTIVE
    nuevas = [
        a for a in alertas
        if a.get("id") and a["id"] not in sent_ids
        and (a.get("status") or "").upper() == "ACTIVE"
    ]

    if not nuevas:
        activas_total = sum(1 for a in alertas if (a.get("status") or "").upper() == "ACTIVE")
        print(f"   No hay alertas nuevas activas ({activas_total} activas ya conocidas)")
        return 0

    print(f"   {len(nuevas)} alerta(s) nueva(s) activa(s) detectada(s)")

    # 3. Enviar cada alerta nueva en un mensaje separado
    enviadas = 0
    for i, alerta in enumerate(nuevas, 1):
        try:
            send_single_alert(alerta)
            sent_ids.add(alerta["id"])
            save_sent_ids(sent_ids)
            enviadas += 1
            titulo = (alerta.get("title") or "Sin título")[:50]
            print(f"   ✅ [{i}/{len(nuevas)}] Enviada: {titulo}...")
            # Pequeña pausa entre mensajes para evitar rate limits
            if i < len(nuevas):
                time.sleep(2)
        except Exception as e:
            print(f"   ❌ Error enviando alerta {alerta.get('id')}: {e}")

    return enviadas


def main():
    run_once = "--once" in sys.argv or "-1" in sys.argv
    if run_once:
        # Modo cron: ejecutar un solo ciclo y salir
        try:
            run_cycle()
        except Exception as e:
            print(f"\n❌ Error en ciclo: {e}")
            sys.exit(1)
        return

    print("🚀 Monitor de alertas Aliado")
    print(f"   Intervalo: cada {INTERVAL_SECONDS // 60} minutos")
    print(f"   Grupo configurado: {'WHAPI_GROUP_ID' in __import__('os').environ}")
    print("   Presiona Ctrl+C para detener\n")

    while True:
        try:
            run_cycle()
        except KeyboardInterrupt:
            print("\n\n⏹️  Monitor detenido por el usuario")
            break
        except Exception as e:
            print(f"\n❌ Error en ciclo: {e}")

        print(f"\n⏳ esperando {INTERVAL_SECONDS // 60} minutos...")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
