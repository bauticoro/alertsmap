#!/usr/bin/env python3
"""
Script para obtener alertas neuralgicas de Aliado recorriendo todo México
dividiendo el territorio en bounding boxes.
"""

import json
import random
import subprocess
import sys
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path

# User-Agents de navegadores desktop comunes (rotación para parecer tráfico variado)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

# Coordenadas aproximadas de México (bounding box completo)
# Norte: frontera con USA ~32.7
# Sur: frontera con Guatemala ~14.5
# Este: Yucatán ~-86.7
# Oeste: Baja California ~-118.4
MEXICO_BOUNDS = {
    "min_lat": 14.5,
    "max_lat": 32.7,
    "min_lon": -118.4,
    "max_lon": -86.7,
}

# Tamaño de cada celda del grid (en grados)
# Ajustar según necesidad: más pequeño = más requests pero cobertura más fina
LAT_STEP = 3.0  # grados de latitud por celda
LON_STEP = 3.0  # grados de longitud por celda

API_URL = "https://alertas.aliado.alephri.com/api/graphql"
BEARER_TOKEN = "e2e29d3164218e91ea40dd6c63808b79"

GRAPHQL_QUERY = """
fragment NeuralgicAlertCoreFields on NeuralgicAlert {
  id
  title
  description
  latlon {
    lat
    lon
    __typename
  }
  __typename
}

query GET_NEURALGIC_ALERTS_FOR_LIST($filters: NeuralgicAlertsFiltersInput, $first: Int) {
  neuralgicAlerts(filters: $filters, first: $first) {
    edges {
      node {
        ...NeuralgicAlertCoreFields
        drawings
        photos
        status
        alertType {
          id
          name
          __typename
        }
        __typename
      }
      __typename
    }
    __typename
  }
}
"""


def get_date_range(days_back: int = 1):
    """Genera el rango de fechas para el filtro."""
    end = datetime.utcnow()
    start = end - timedelta(days=days_back)
    return {
        "startDatetime": start.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "endDatetime": end.strftime("%Y-%m-%dT%H:%M:%S.999Z"),
    }


def generate_bounding_boxes():
    """Genera todos los bounding boxes que cubren México."""
    boxes = []
    lat = MEXICO_BOUNDS["min_lat"]
    while lat < MEXICO_BOUNDS["max_lat"]:
        lon = MEXICO_BOUNDS["min_lon"]
        while lon < MEXICO_BOUNDS["max_lon"]:
            bottom_left = {
                "lat": lat,
                "lon": lon,
            }
            top_right = {
                "lat": min(lat + LAT_STEP, MEXICO_BOUNDS["max_lat"]),
                "lon": min(lon + LON_STEP, MEXICO_BOUNDS["max_lon"]),
            }
            boxes.append({
                "bottomLeft": bottom_left,
                "topRight": top_right,
            })
            lon += LON_STEP
        lat += LAT_STEP
    return boxes


def _get_headers() -> dict:
    """Headers que imitan un navegador desktop real, sin fingerprinting."""
    return {
        "accept": "*/*",
        "accept-language": random.choice([
            "es-MX,es;q=0.9,en;q=0.8",
            "es-ES,es;q=0.9,en;q=0.8",
            "es,en-US;q=0.9,en;q=0.8",
        ]),
        "accept-encoding": "gzip, deflate, br",
        "authorization": f"Bearer {BEARER_TOKEN}",
        "content-type": "application/json",
        "origin": "https://ui.aliado.alephri.com",
        "referer": "https://ui.aliado.alephri.com/",
        "user-agent": random.choice(USER_AGENTS),
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
    }


def fetch_alerts_for_box(session: requests.Session, bounding_box: dict, date_range: dict) -> list:
    """Hace la petición a la API para un bounding box específico."""
    headers = _get_headers()
    payload = {
        "operationName": "GET_NEURALGIC_ALERTS_FOR_LIST",
        "variables": {
            "filters": {
                "boundingBox": bounding_box,
                **date_range,
            },
            "first": 100,
        },
        "query": GRAPHQL_QUERY.strip(),
    }
    try:
        resp = session.post(API_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        edges = data.get("data", {}).get("neuralgicAlerts", {}).get("edges", [])
        return [e["node"] for e in edges]
    except requests.RequestException as e:
        print(f"  Error en request: {e}")
        return []
    except json.JSONDecodeError as e:
        print(f"  Error parseando JSON: {e}")
        return []


def main():
    date_range = get_date_range(days_back=1)
    boxes = generate_bounding_boxes()
    random.shuffle(boxes)  # Orden aleatorio para no parecer barrido sistemático
    print(f"Recorriendo {len(boxes)} bounding boxes sobre México")
    print(f"Rango de fechas: {date_range['startDatetime']} -> {date_range['endDatetime']}")
    print("-" * 60)

    all_alerts = []
    seen_ids = set()
    session = requests.Session()

    # Pequeña pausa inicial para no parecer arranque automático
    time.sleep(random.uniform(0.5, 2.0))

    for i, box in enumerate(boxes):
        bl = box["bottomLeft"]
        tr = box["topRight"]
        print(f"[{i+1}/{len(boxes)}] Box: lat [{bl['lat']:.2f},{tr['lat']:.2f}] lon [{bl['lon']:.2f},{tr['lon']:.2f}]", end=" ")
        alerts = fetch_alerts_for_box(session, box, date_range)
        new_count = 0
        for a in alerts:
            if a["id"] not in seen_ids:
                seen_ids.add(a["id"])
                all_alerts.append(a)
                new_count += 1
        print(f"-> {len(alerts)} alertas ({new_count} nuevas)")
        # Pausa aleatoria entre requests para parecer uso humano (no patrón fijo)
        time.sleep(random.uniform(1.5, 4.5))

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"alertas_mexico_{timestamp}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_alerts, f, ensure_ascii=False, indent=2)
    print("-" * 60)
    print(f"Total de alertas únicas: {len(all_alerts)}")
    print(f"Guardado en: {output_file}")

    # Generar mapa con las alertas
    if all_alerts:
        script_dir = Path(__file__).parent
        result = subprocess.run(
            [sys.executable, str(script_dir / "mapa_alertas.py"), str(output_file)],
            cwd=str(script_dir),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(result.stdout.strip())
        else:
            print("Para generar el mapa: pip install folium && python3 mapa_alertas.py")


if __name__ == "__main__":
    main()
