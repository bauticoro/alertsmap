#!/usr/bin/env python3
"""
Script para enviar mensajes a WhatsApp usando la API de Whapi.
"""
import base64
import io
import json
import os
import random
import requests
import sys
from pathlib import Path
from typing import Optional, Tuple, Union

import staticmaps
from staticmaps import tile_provider

WHAPI_BASE_URL = "https://gate.whapi.cloud"
GROUP_ID = os.environ.get("WHAPI_GROUP_ID", "")
TOKEN = os.environ.get("WHAPI_TOKEN", "")

MAP_WIDTH = 640
MAP_HEIGHT = 480
MAP_ZOOM = 15


def format_alert(alert: dict) -> str:
    """Formatea una alerta para enviar por WhatsApp."""
    title = alert.get("title", "Alerta")
    description = alert.get("description", "")
    return f"{title}\n\n{description}".strip()


def get_alert_location(alert: dict) -> Optional[Tuple[float, float]]:
    """Extrae lat/lon de una alerta si está disponible."""
    latlon = alert.get("latlon")
    if not latlon:
        return None
    lat = latlon.get("lat")
    lon = latlon.get("lon")
    if lat is None or lon is None:
        return None
    return (float(lat), float(lon))


def generate_map_image(lat: float, lon: float) -> bytes:
    """Genera una imagen PNG del mapa con un marcador en la ubicación indicada."""
    context = staticmaps.Context()
    context.set_tile_provider(tile_provider.tile_provider_OSM)
    point = staticmaps.create_latlng(lat, lon)
    context.add_object(staticmaps.Marker(point, color=staticmaps.RED, size=14))
    context.set_zoom(MAP_ZOOM)
    context.set_center(point)
    image = context.render_pillow(MAP_WIDTH, MAP_HEIGHT)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def send_image_with_caption(image_bytes: bytes, caption: str) -> dict:
    """Envía una imagen con caption al grupo de WhatsApp."""
    if not TOKEN or not GROUP_ID:
        raise ValueError("Configura WHAPI_TOKEN y WHAPI_GROUP_ID como variables de entorno")
    url = f"{WHAPI_BASE_URL}/messages/image"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    media = f"data:image/png;name=mapa_gps.png;base64,{b64}"
    payload = {
        "to": GROUP_ID,
        "media": media,
        "caption": caption,
    }
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


def send_alert(alertas_path: Optional[Union[str, Path]] = None) -> dict:
    """Carga alertas del JSON, elige una al azar y la envía con mapa GPS."""
    path = Path(alertas_path) if alertas_path else Path(__file__).parent / "output"
    json_files = list(path.glob("alertas_*.json"))
    if not json_files:
        raise FileNotFoundError(f"No se encontraron archivos de alertas en {path}")
    with open(json_files[-1]) as f:  # el más reciente
        alertas = json.load(f)
    # Filtrar solo alertas con ubicación para el mapa
    alertas_con_ubicacion = [a for a in alertas if get_alert_location(a)]
    if not alertas_con_ubicacion:
        alertas_con_ubicacion = alertas  # fallback: enviar sin mapa
    alerta = random.choice(alertas_con_ubicacion)
    mensaje = format_alert(alerta)
    location = get_alert_location(alerta)
    if location:
        lat, lon = location
        map_image = generate_map_image(lat, lon)
        return send_image_with_caption(map_image, mensaje)
    return send_message(mensaje)


def send_message(message: str) -> dict:
    """Envía un mensaje de texto al grupo de WhatsApp."""
    if not TOKEN or not GROUP_ID:
        raise ValueError("Configura WHAPI_TOKEN y WHAPI_GROUP_ID como variables de entorno")
    url = f"{WHAPI_BASE_URL}/messages/text"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "to": GROUP_ID,
        "body": message,
    }
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    if "--alert" in sys.argv or "-a" in sys.argv:
        try:
            result = send_alert()
            print("✅ Alerta enviada correctamente:", result)
        except Exception as e:
            print("❌ Error:", e)
            sys.exit(1)
    else:
        message = sys.argv[1] if len(sys.argv) > 1 else "Hola! Mensaje de prueba desde el Scraper de Aliado."
        try:
            result = send_message(message)
            print("✅ Mensaje enviado correctamente:", result)
        except requests.exceptions.RequestException as e:
            print("❌ Error al enviar:", e)
            if hasattr(e, "response") and e.response is not None:
                print("Respuesta:", e.response.text)
            sys.exit(1)
