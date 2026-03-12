#!/usr/bin/env python3
"""
Script para obtener alertas neuralgicas de Aliado para todo México
en una sola petición a la API.

Optimizado para ser indetectable: TLS fingerprinting (curl_cffi), headers
completos tipo navegador y retry con backoff.
"""

import json
import random
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    from curl_cffi import requests as curl_requests
    USE_CURL_CFFI = True
except ImportError:
    import requests as curl_requests
    USE_CURL_CFFI = False

# Targets de impersonación para curl_cffi (TLS/JA3 fingerprint de navegadores reales)
# Rotamos entre ellos para variar el fingerprint entre ejecuciones
IMPERSONATE_TARGETS = [
    "chrome120",
    "chrome119",
    "chrome116",
    "safari180",
    "safari180_ios",
    "edge101",
]

# User-Agents coherentes con cada impersonate (para cuando curl_cffi no los añade)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
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

# Máximo de alertas por request (la API soporta hasta ~500)
FIRST = 500

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

query GET_NEURALGIC_ALERTS_FOR_LIST($filters: NeuralgicAlertsFiltersInput, $first: Int, $after: String) {
  neuralgicAlerts(filters: $filters, first: $first, after: $after) {
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
    pageInfo {
      hasNextPage
      endCursor
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


def get_mexico_bounding_box():
    """Devuelve el bounding box completo de México."""
    return {
        "bottomLeft": {"lat": MEXICO_BOUNDS["min_lat"], "lon": MEXICO_BOUNDS["min_lon"]},
        "topRight": {"lat": MEXICO_BOUNDS["max_lat"], "lon": MEXICO_BOUNDS["max_lon"]},
    }


def _get_headers(impersonate: Optional[str] = None) -> dict:
    """Headers completos que coinciden con el TLS fingerprint del navegador."""
    base = {
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
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
    }
    # sec-ch-ua solo para Chrome/Edge (Safari no los envía)
    if impersonate and ("chrome" in impersonate or "edge" in impersonate):
        base["sec-ch-ua"] = '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"'
        base["sec-ch-ua-mobile"] = "?0"
        base["sec-ch-ua-platform"] = random.choice(['"Windows"', '"macOS"'])
        base["priority"] = "u=1, i"
    base["user-agent"] = random.choice(USER_AGENTS)
    return base


def is_inside_mexico(latlon: Optional[dict]) -> bool:
    """Verifica si las coordenadas están dentro de los límites de México."""
    if not latlon or "lat" not in latlon or "lon" not in latlon:
        return False
    lat = latlon["lat"]
    lon = latlon["lon"]
    return (
        MEXICO_BOUNDS["min_lat"] <= lat <= MEXICO_BOUNDS["max_lat"]
        and MEXICO_BOUNDS["min_lon"] <= lon <= MEXICO_BOUNDS["max_lon"]
    )


def fetch_all_alerts(session, bounding_box: dict, date_range: dict, impersonate: Optional[str]) -> list:
    """Obtiene todas las alertas de México en una o más peticiones (con paginación si hace falta)."""
    all_nodes = []
    after_cursor = None
    page = 1

    while True:
        headers = _get_headers(impersonate)
        payload = {
            "operationName": "GET_NEURALGIC_ALERTS_FOR_LIST",
            "variables": {
                "filters": {
                    "boundingBox": bounding_box,
                    **date_range,
                },
                "first": FIRST,
                "after": after_cursor,
            },
            "query": GRAPHQL_QUERY.strip(),
        }
        timeout = random.uniform(25, 45)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                kwargs = {"headers": headers, "json": payload, "timeout": timeout}
                if USE_CURL_CFFI and impersonate:
                    kwargs["impersonate"] = impersonate
                resp = session.post(API_URL, **kwargs)
                if resp.status_code == 429:
                    wait = (2 ** attempt) + random.uniform(5, 15)
                    print(f"  Rate limit (429), esperando {wait:.1f}s...")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                alerts_data = data.get("data", {}).get("neuralgicAlerts", {})
                edges = alerts_data.get("edges", [])
                page_info = alerts_data.get("pageInfo", {})

                nodes = [e["node"] for e in edges]
                all_nodes.extend(nodes)

                if page == 1:
                    print(f"  Página 1: {len(nodes)} alertas", end="")
                else:
                    print(f"  Página {page}: +{len(nodes)} alertas", end="")

                if not page_info.get("hasNextPage"):
                    print()
                    return all_nodes

                after_cursor = page_info.get("endCursor")
                page += 1
                time.sleep(random.uniform(0.5, 1.5))  # Pausa breve entre páginas
                break

            except Exception as e:
                if attempt < max_retries - 1:
                    backoff = (2 ** attempt) + random.uniform(1, 4)
                    print(f"  Error: {e}, reintento en {backoff:.1f}s...")
                    time.sleep(backoff)
                else:
                    print(f"  Error en request: {e}")
                    return all_nodes

    return all_nodes


def main():
    date_range = get_date_range(days_back=1)
    bounding_box = get_mexico_bounding_box()
    impersonate = random.choice(IMPERSONATE_TARGETS) if USE_CURL_CFFI else None

    print("Obteniendo alertas de todo México (una sola carga)")
    print(f"Rango de fechas: {date_range['startDatetime']} -> {date_range['endDatetime']}")
    if USE_CURL_CFFI:
        print(f"Fingerprint: {impersonate}")
    else:
        print("(curl_cffi no instalado, usando requests estándar)")
    print("-" * 60)

    session = curl_requests.Session()
    raw_alerts = fetch_all_alerts(session, bounding_box, date_range, impersonate)

    # Filtrar dentro de México y deduplicar por id
    seen_ids = set()
    all_alerts = []
    for a in raw_alerts:
        if a["id"] not in seen_ids and is_inside_mexico(a.get("latlon")):
            seen_ids.add(a["id"])
            all_alerts.append(a)

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    # Añadir región a cada alerta
    try:
        from regiones_mexico import identificar_region
        for a in all_alerts:
            info = identificar_region(a, use_reverse_geocode=False)
            a["region"] = info["region"]
            a["estado"] = info.get("estado")
    except ImportError:
        pass

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
