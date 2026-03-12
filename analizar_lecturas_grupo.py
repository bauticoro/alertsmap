#!/usr/bin/env python3
"""
Script para analizar la cantidad de lecturas de cada mensaje enviado a los grupos
de WhatsApp (Chofex - Alertas de Tráfico). Muestra qué tan utilizado está cada grupo
y aproxima cada cuánto tiempo abre el grupo cada persona (basado en lecturas).

Usa la API de Whapi para:
1. Obtener los mensajes enviados por nosotros en cada grupo
2. Consultar el estado de lectura de cada mensaje (statuses)
3. Generar estadísticas de engagement y frecuencia de apertura por persona
4. Subir el resultado a GitHub (web/estadisticas_grupo.json)

Requiere: WHAPI_TOKEN, GITHUB_TOKEN (para push) en .env
"""

import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

WHAPI_BASE_URL = os.environ.get("WHAPI_BASE_URL", "https://gate.whapi.cloud").rstrip("/")
TOKEN = os.environ.get("WHAPI_TOKEN", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

SCRIPT_DIR = Path(__file__).parent
WEB_STATS_JSON = SCRIPT_DIR / "web" / "estadisticas_grupo.json"

# Grupos a analizar (mismos que en send_whatsapp.py)
GROUP_ID_TODAS = "120363423858096188@g.us"
REGION_TO_GROUP_ID = {
    "Noroeste": "120363425848060105@g.us",
    "Noreste": "120363405662247678@g.us",
    "Oriente": "120363408065348424@g.us",
    "Occidente": "120363423512607360@g.us",
    "Centrosur": "120363407742793121@g.us",
    "Centronorte": "120363406700206245@g.us",
    "Suroeste": "120363425712379462@g.us",
    "Sureste": "120363406619538678@g.us",
}

# chat_id -> nombre para iterar
ALL_GROUPS = {
    GROUP_ID_TODAS: "Todas las regiones",
    **{chat_id: region for region, chat_id in REGION_TO_GROUP_ID.items()},
}


def get_messages(chat_id: str, count: int = 100, from_me: bool = True) -> list:
    """Obtiene los mensajes enviados por nosotros en un chat."""
    if not TOKEN:
        raise ValueError("Configura WHAPI_TOKEN en .env")
    url = f"{WHAPI_BASE_URL}/messages/list/{chat_id}"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    params = {"count": count, "from_me": str(from_me).lower(), "sort": "desc"}
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("messages", [])


def get_message_statuses(message_id: str) -> list:
    """Obtiene los estados de lectura/entrega de un mensaje.
    Retorna lista de statuses (cada uno puede ser read, delivered, sent, etc.)
    Para grupos: cada status con 'read' y viewer_id = una persona que leyó.
    """
    if not TOKEN:
        raise ValueError("Configura WHAPI_TOKEN en .env")
    url = f"{WHAPI_BASE_URL}/statuses/{message_id}"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 403:
            # "View statuses available only for outgoing messages"
            return []
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        return data.get("statuses", [])
    except requests.exceptions.RequestException:
        return []


def count_reads(statuses: list) -> int:
    """Cuenta cuántas personas han leído el mensaje (status=read, viewer_id único)."""
    readers = set()
    for s in statuses:
        if (s.get("status") or "").lower() == "read" and s.get("viewer_id"):
            readers.add(s["viewer_id"])
    return len(readers)


def extract_read_events(statuses: list) -> List[Tuple[str, float]]:
    """Extrae (viewer_id, timestamp) de cada lectura para análisis de frecuencia."""
    events = []
    for s in statuses:
        if (s.get("status") or "").lower() != "read" or not s.get("viewer_id"):
            continue
        ts = s.get("timestamp")
        if ts is None:
            continue
        if isinstance(ts, str):
            try:
                ts = float(ts)
            except ValueError:
                continue
        events.append((s["viewer_id"], float(ts)))
    return events


def compute_frequency_per_person(events: List[Tuple[str, float]]) -> dict:
    """
    Calcula cada cuánto tiempo abre el grupo cada persona.
    events: [(viewer_id, timestamp), ...]
    Retorna: {viewer_id: {avg_hours, avg_human, read_count, intervals_count}}
    """
    by_person: dict[str, list[float]] = defaultdict(list)
    for vid, ts in events:
        by_person[vid].append(ts)

    result = {}
    for vid, timestamps in by_person.items():
        timestamps = sorted(set(timestamps))
        if len(timestamps) < 2:
            result[vid] = {
                "avg_hours": None,
                "avg_human": "solo 1 lectura",
                "read_count": len(timestamps),
                "intervals_count": 0,
            }
            continue
        gaps_seconds = [
            timestamps[i + 1] - timestamps[i]
            for i in range(len(timestamps) - 1)
        ]
        avg_seconds = sum(gaps_seconds) / len(gaps_seconds)
        avg_hours = avg_seconds / 3600
        if avg_hours < 1:
            avg_human = f"cada {avg_hours * 60:.0f} min"
        elif avg_hours < 24:
            avg_human = f"cada {avg_hours:.1f} h"
        else:
            avg_days = avg_hours / 24
            avg_human = f"cada {avg_days:.1f} días"
        result[vid] = {
            "avg_hours": round(avg_hours, 2),
            "avg_human": avg_human,
            "read_count": len(timestamps),
            "intervals_count": len(gaps_seconds),
        }
    return result


def mask_viewer_id(vid: str) -> str:
    """Enmascara el ID para privacidad (solo últimos 2 dígitos visibles)."""
    if not vid or len(vid) < 4:
        return "****"
    return vid[:2] + "*" * (len(vid) - 4) + vid[-2:]


def analyze_group(chat_id: str, group_name: str, max_messages: int = 50) -> dict:
    """Analiza los mensajes de un grupo y retorna estadísticas + frecuencia de apertura por persona."""
    print(f"  📥 Obteniendo mensajes de '{group_name}'...")
    messages = get_messages(chat_id, count=min(max_messages, 500), from_me=True)
    if not messages:
        return {
            "group_name": group_name,
            "chat_id": chat_id,
            "total_messages": 0,
            "messages_analyzed": 0,
            "total_reads": 0,
            "avg_reads_per_message": 0,
            "messages_with_reads": 0,
            "message_details": [],
            "frequency_per_person": [],
        }

    message_details = []
    total_reads = 0
    messages_with_reads = 0
    all_read_events: List[Tuple[str, float]] = []

    for i, msg in enumerate(messages):
        msg_id = msg.get("id")
        if not msg_id:
            continue
        # Pequeña pausa para no saturar la API
        if i > 0:
            time.sleep(0.3)
        statuses = get_message_statuses(msg_id)
        reads = count_reads(statuses)
        total_reads += reads
        if reads > 0:
            messages_with_reads += 1
        all_read_events.extend(extract_read_events(statuses))

        # Preview del contenido (caption o body)
        preview = ""
        if msg.get("type") == "image" and msg.get("caption"):
            preview = (msg["caption"] or "")[:80] + ("..." if len(msg.get("caption", "")) > 80 else "")
        elif msg.get("body"):
            preview = (msg["body"] or "")[:80] + ("..." if len(msg.get("body", "")) > 80 else "")

        ts = msg.get("timestamp")
        if isinstance(ts, (int, float)):
            try:
                dt = datetime.fromtimestamp(ts)
                ts_str = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, OSError):
                ts_str = str(ts)
        else:
            ts_str = str(ts) if ts else ""

        message_details.append({
            "id": msg_id,
            "timestamp": ts_str,
            "reads": reads,
            "preview": preview or "(sin texto)",
        })

    n = len(message_details)
    avg = total_reads / n if n > 0 else 0

    # Frecuencia de apertura por persona (cada cuánto abre el grupo)
    freq_data = compute_frequency_per_person(all_read_events)
    frequency_per_person = [
        {
            "viewer_id_masked": mask_viewer_id(vid),
            "avg_human": info["avg_human"],
            "avg_hours": info["avg_hours"],
            "read_count": info["read_count"],
        }
        for vid, info in sorted(
            freq_data.items(),
            key=lambda x: (x[1]["avg_hours"] or 999999, -x[1]["read_count"]),
        )
    ]

    return {
        "group_name": group_name,
        "chat_id": chat_id,
        "total_messages": len(messages),
        "messages_analyzed": n,
        "total_reads": total_reads,
        "avg_reads_per_message": round(avg, 1),
        "messages_with_reads": messages_with_reads,
        "message_details": message_details,
        "frequency_per_person": frequency_per_person,
    }


def print_report(results: list, verbose: bool = False):
    """Imprime el reporte de análisis."""
    print("\n" + "=" * 70)
    print("📊 ANÁLISIS DE LECTURAS POR GRUPO - Chofex Alertas de Tráfico")
    print("=" * 70)

    # Resumen global
    total_msgs = sum(r["messages_analyzed"] for r in results)
    total_reads = sum(r["total_reads"] for r in results)
    overall_avg = total_reads / total_msgs if total_msgs > 0 else 0

    print(f"\n📈 Resumen global: {total_msgs} mensajes analizados, {total_reads} lecturas totales")
    print(f"   Promedio general: {overall_avg:.1f} lecturas por mensaje\n")

    # Por grupo
    for r in sorted(results, key=lambda x: x["avg_reads_per_message"], reverse=True):
        name = r["group_name"]
        n = r["messages_analyzed"]
        reads = r["total_reads"]
        avg = r["avg_reads_per_message"]
        with_reads = r["messages_with_reads"]

        bar_len = min(40, max(0, int(avg)))
        bar = "█" * bar_len + "░" * (40 - bar_len)

        print(f"  {name}")
        print(f"    Mensajes: {n}  |  Lecturas totales: {reads}  |  Promedio: {avg}  |  Con al menos 1 lectura: {with_reads}")
        print(f"    [{bar}]")

        # Frecuencia de apertura (cada cuánto abre cada persona)
        freq = r.get("frequency_per_person", [])
        if freq:
            print(f"    ⏱️  Frecuencia de apertura (aprox. cada cuánto abre cada persona):")
            for p in freq[:8]:
                print(f"       • {p['viewer_id_masked']}: {p['avg_human']} ({p['read_count']} lecturas)")
            if len(freq) > 8:
                print(f"       ... y {len(freq) - 8} más")
        print()

        if verbose and r["message_details"]:
            print("    Detalle de mensajes (últimos):")
            for m in r["message_details"][:10]:
                print(f"      • {m['timestamp']}: {m['reads']} lecturas - {m['preview'][:50]}...")
            if len(r["message_details"]) > 10:
                print(f"      ... y {len(r['message_details']) - 10} más")
            print()

    print("=" * 70)


def save_json_report(results: list, output_path: Path) -> None:
    """Guarda el reporte en JSON."""
    report = {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_messages": sum(r["messages_analyzed"] for r in results),
            "total_reads": sum(r["total_reads"] for r in results),
        },
        "groups": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Reporte guardado en: {output_path}")


def push_to_github() -> bool:
    """
    Sube web/estadisticas_grupo.json a GitHub.
    Requiere GITHUB_TOKEN en .env.
    """
    if not GITHUB_TOKEN:
        print("   ⚠️ GITHUB_TOKEN no configurado, no se sube a GitHub")
        return False
    if not (SCRIPT_DIR / ".git").exists():
        print("   ⚠️ No es un repo git")
        return False
    if not WEB_STATS_JSON.exists():
        print("   ⚠️ web/estadisticas_grupo.json no existe")
        return False

    try:
        r = subprocess.run(
            ["git", "status", "--porcelain", str(WEB_STATS_JSON)],
            cwd=str(SCRIPT_DIR),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode != 0:
            return False
        if not r.stdout.strip():
            print("   ℹ️ Sin cambios en estadisticas_grupo.json")
            return True

        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(SCRIPT_DIR),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if remote.returncode == 0 and "x-access-token" not in (remote.stdout or "") and GITHUB_TOKEN not in (remote.stdout or ""):
            url = (remote.stdout or "").strip()
            if url.startswith("https://github.com/"):
                url = url.replace("https://", f"https://x-access-token:{GITHUB_TOKEN}@", 1)
            elif url.startswith("http://github.com/"):
                url = url.replace("http://", f"http://x-access-token:{GITHUB_TOKEN}@", 1)
            subprocess.run(
                ["git", "remote", "set-url", "origin", url],
                cwd=str(SCRIPT_DIR),
                capture_output=True,
                timeout=5,
            )

        subprocess.run(
            ["git", "add", str(WEB_STATS_JSON)],
            cwd=str(SCRIPT_DIR),
            capture_output=True,
            check=True,
            timeout=5,
        )
        commit = subprocess.run(
            ["git", "commit", "-m", "chore: actualizar estadísticas de lecturas del grupo"],
            cwd=str(SCRIPT_DIR),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if commit.returncode != 0 and "nothing to commit" not in (commit.stderr or "").lower():
            return False

        result = subprocess.run(
            ["git", "push", "origin", "HEAD"],
            cwd=str(SCRIPT_DIR),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            print("   ✅ Estadísticas subidas a GitHub")
            return True
        print(f"   ⚠️ Git push falló: {(result.stderr or result.stdout or '')[:200]}")
        return False
    except subprocess.TimeoutExpired:
        print("   ⚠️ Timeout en git push")
        return False
    except Exception as e:
        print(f"   ⚠️ Error subiendo a GitHub: {e}")
        return False


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    no_push = "--no-push" in sys.argv
    max_messages = 50
    for arg in sys.argv[1:]:
        if arg.startswith("--max="):
            try:
                max_messages = int(arg.split("=")[1])
            except ValueError:
                pass

    if not TOKEN:
        print("❌ Error: Configura WHAPI_TOKEN en tu archivo .env")
        sys.exit(1)

    print("🔍 Analizando lecturas de mensajes en los grupos de WhatsApp...")
    results = []

    for chat_id, group_name in ALL_GROUPS.items():
        try:
            r = analyze_group(chat_id, group_name, max_messages=max_messages)
            results.append(r)
        except requests.exceptions.HTTPError as e:
            print(f"  ⚠️ Error en {group_name}: {e}")
            if hasattr(e, "response") and e.response is not None:
                try:
                    err = e.response.json()
                    print(f"     {err.get('error', {}).get('message', e.response.text)}")
                except Exception:
                    print(f"     {e.response.text[:200]}")
        except Exception as e:
            print(f"  ⚠️ Error en {group_name}: {e}")
        time.sleep(0.5)  # Pausa entre grupos

    if not results:
        print("❌ No se pudo analizar ningún grupo.")
        sys.exit(1)

    print_report(results, verbose=verbose)

    # Guardar en web/estadisticas_grupo.json (para consumo web y GitHub)
    save_json_report(results, WEB_STATS_JSON)

    # Subir a GitHub
    if not no_push:
        push_to_github()
    else:
        print("   ℹ️ --no-push: no se subió a GitHub")


if __name__ == "__main__":
    main()
