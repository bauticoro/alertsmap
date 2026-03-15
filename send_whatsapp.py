#!/usr/bin/env python3
"""
Script para enviar mensajes a WhatsApp usando la API de Whapi.
"""
import io
import json
import os
import random
import requests
import sys
from pathlib import Path
from typing import Optional, Tuple, Union

import staticmaps
from openai import OpenAI
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

WHAPI_BASE_URL = os.environ.get("WHAPI_BASE_URL", "https://gate.whapi.cloud").rstrip("/")
GROUP_ID = os.environ.get("WHAPI_GROUP_ID", "")
TOKEN = os.environ.get("WHAPI_TOKEN", "")

# Grupo donde se envían TODAS las alertas (además del grupo por región)
GROUP_ID_TODAS = "120363423858096188@g.us"

# Grupo de WhatsApp por región (Chofex - Alertas de Tráfico)
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
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

MAP_WIDTH = 640
MAP_HEIGHT = 480
MAP_ZOOM = 8

# Tile provider OSM sin atribución (reemplazamos por branding Chofex)
TILE_PROVIDER_OSM_NO_ATTRIBUTION = staticmaps.TileProvider(
    "osm",
    url_pattern="https://$s.tile.openstreetmap.org/$z/$x/$y.png",
    shards=["a", "b", "c"],
    attribution=None,
    max_zoom=19,
)

CHOFEX_LOGO_URL = "https://www.chofex.com/assets/logo-chofex-color-O6e_H_to.png"
MAPA_ALERTAS_URL = "https://mapadealertas.chofex.com/"
_logo_cache: Optional[bytes] = None


def _get_chofex_logo() -> Optional[bytes]:
    """Obtiene el logo de Chofex (cache en memoria)."""
    global _logo_cache
    if _logo_cache is not None:
        return _logo_cache
    try:
        resp = requests.get(CHOFEX_LOGO_URL, timeout=10)
        resp.raise_for_status()
        _logo_cache = resp.content
        return _logo_cache
    except Exception:
        return None


def _append_map_link(text: str) -> str:
    """Añade el link al mapa de alertas al final del mensaje."""
    if not text.strip():
        return text
    return f"{text.strip()}\n\n📍 Mapa: {MAPA_ALERTAS_URL}"


def format_alert(alert: dict) -> str:
    """Formatea una alerta para enviar por WhatsApp."""
    title = alert.get("title", "Alerta")
    description = alert.get("description", "")
    return f"{title}\n\n{description}".strip()


def paraphrase_text(text: str) -> str:
    """Parafrasea el texto usando OpenAI para que no sea idéntico al original.
    Mantiene el significado, emojis y estructura. Si falla o no hay API key, devuelve el original.
    """
    if not text.strip():
        return text
    if not OPENAI_API_KEY:
        return text
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un reescritor de textos. Parafrasea el mensaje que recibes manteniendo "
                        "exactamente el mismo significado e información (ubicaciones, distancias, consejos). "
                        "Usa palabras y estructuras diferentes. Conserva los emojis y el formato de saltos "
                        "de línea. Responde ÚNICAMENTE con el texto parafraseado, sin explicaciones."
                    ),
                },
                {"role": "user", "content": text},
            ],
            temperature=0.7,
        )
        result = response.choices[0].message.content.strip()
        return result if result else text
    except Exception:
        return text


def get_group_id_for_alert(alert: dict) -> Optional[str]:
    """Obtiene el group_id de WhatsApp según la región de la alerta.
    Retorna None si la región no tiene grupo (Guatemala, Desconocida) o no se puede determinar.
    """
    region = alert.get("region")
    if not region or region == "Desconocida" or "no aplica" in (region or "").lower():
        try:
            from regiones_mexico import identificar_region
            info = identificar_region(alert, use_reverse_geocode=True)
            region = info.get("region")
        except ImportError:
            pass
    if region and region in REGION_TO_GROUP_ID:
        return REGION_TO_GROUP_ID[region]
    return None


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


def _add_chofex_overlay(image: Image.Image) -> Image.Image:
    """Añade logo y texto 'Alerta reportada por Chofex' en la esquina inferior del mapa."""
    w, h = image.size
    img_rgba = image.convert("RGBA")

    # Barra inferior semi-transparente
    overlay_height = 44
    overlay = Image.new("RGBA", image.size, (255, 255, 255, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle(
        [(0, h - overlay_height), (w, h)],
        fill=(255, 255, 255, 230),
    )
    img_rgba = Image.alpha_composite(img_rgba, overlay)

    # Logo Chofex
    logo_bytes = _get_chofex_logo()
    if logo_bytes:
        try:
            logo_img = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
            logo_h = 28
            logo_w = int(logo_img.width * logo_h / logo_img.height)
            logo_img = logo_img.resize((logo_w, logo_h), Image.LANCZOS)
            x_logo = 8
            y_logo = h - overlay_height + (overlay_height - logo_h) // 2
            img_rgba.paste(logo_img, (x_logo, y_logo), logo_img)
        except Exception:
            pass

    # Texto "Alerta reportada por Chofex"
    draw = ImageDraw.Draw(img_rgba)
    text = "Alerta reportada por Chofex"
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
    except OSError:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
        except OSError:
            font = ImageFont.load_default()
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_w = text_bbox[2] - text_bbox[0]
    x_text = w - text_w - 12
    y_text = h - overlay_height + (overlay_height - (text_bbox[3] - text_bbox[1])) // 2
    draw.text((x_text, y_text), text, fill=(0, 0, 0, 255), font=font)

    return img_rgba.convert("RGB")


def generate_map_image(lat: float, lon: float) -> bytes:
    """Genera una imagen PNG del mapa con un marcador en la ubicación indicada.
    Sin atribución OpenStreetMap; incluye branding Chofex (logo + texto).
    """
    context = staticmaps.Context()
    context.set_tile_provider(TILE_PROVIDER_OSM_NO_ATTRIBUTION)
    cache_dir = str(Path(__file__).parent / ".cache" / "tiles")
    context.set_cache_dir(cache_dir)
    point = staticmaps.create_latlng(lat, lon)
    context.add_object(staticmaps.Marker(point, color=staticmaps.RED, size=14))
    context.set_zoom(MAP_ZOOM)
    context.set_center(point)
    image = context.render_pillow(MAP_WIDTH, MAP_HEIGHT)
    image = _add_chofex_overlay(image.convert("RGBA"))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def send_image_with_caption(image_bytes: bytes, caption: str, group_id: Optional[str] = None) -> dict:
    """Envía una imagen con caption al grupo de WhatsApp.
    Usa multipart/form-data (más fiable). Si falla con 404, lanza la excepción.
    group_id: si se pasa, envía a ese grupo; si no, usa GROUP_ID de env.
    """
    target = group_id or GROUP_ID
    if not TOKEN or not target:
        raise ValueError("Configura WHAPI_TOKEN y WHAPI_GROUP_ID (o group_id) como variables de entorno")
    url = f"{WHAPI_BASE_URL.rstrip('/')}/messages/image"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    data = {"to": target, "caption": caption}
    files = {"media": ("mapa_gps.png", io.BytesIO(image_bytes), "image/png")}
    response = requests.post(url, data=data, files=files, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def send_single_alert(alert: dict) -> Optional[dict]:
    """Envía una alerta al grupo "Todas las regiones" y al grupo de su región (si aplica).
    Siempre envía a Todas las regiones. Si la región tiene grupo propio, también envía ahí.
    Si el envío de imagen falla (ej. 404), envía solo el texto como fallback.
    El texto se parafrasea con OpenAI antes de enviar.
    """
    group_id = get_group_id_for_alert(alert)
    groups_to_send = [GROUP_ID_TODAS]
    if group_id and group_id != GROUP_ID_TODAS:
        groups_to_send.append(group_id)
    mensaje = _append_map_link(paraphrase_text(format_alert(alert)))
    location = get_alert_location(alert)
    result = None
    for gid in groups_to_send:
        try:
            if location:
                try:
                    lat, lon = location
                    map_image = generate_map_image(lat, lon)
                    result = send_image_with_caption(map_image, mensaje, group_id=gid)
                except requests.exceptions.HTTPError as e:
                    if e.response is not None and e.response.status_code in (404, 403):
                        # 404: endpoint no existe; 403: sin permiso para imágenes → fallback a texto
                        result = send_message(mensaje, group_id=gid)
                    else:
                        raise
            else:
                result = send_message(mensaje, group_id=gid)
        except Exception:
            raise
    return result


def send_alert(alertas_path: Optional[Union[str, Path]] = None) -> Optional[dict]:
    """Carga alertas del JSON, elige una al azar y la envía a Todas las regiones (+ grupo por región si aplica)."""
    path = Path(alertas_path) if alertas_path else Path(__file__).parent / "output"
    json_files = [p for p in path.glob("alertas_*.json") if "_con_regiones" not in p.name]
    if not json_files:
        raise FileNotFoundError(f"No se encontraron archivos de alertas en {path}")
    with open(max(json_files, key=lambda p: p.stat().st_mtime)) as f:
        alertas = json.load(f)
    if not alertas:
        raise ValueError("No hay alertas en el archivo")
    alertas_con_ubicacion = [a for a in alertas if get_alert_location(a)]
    if not alertas_con_ubicacion:
        alertas_con_ubicacion = alertas
    alerta = random.choice(alertas_con_ubicacion)
    return send_single_alert(alerta)


def send_message(message: str, group_id: Optional[str] = None) -> dict:
    """Envía un mensaje de texto al grupo de WhatsApp.
    group_id: si se pasa, envía a ese grupo; si no, usa GROUP_ID de env.
    """
    target = group_id or GROUP_ID
    if not TOKEN or not target:
        raise ValueError("Configura WHAPI_TOKEN y WHAPI_GROUP_ID (o group_id) como variables de entorno")
    url = f"{WHAPI_BASE_URL}/messages/text"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "to": target,
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
