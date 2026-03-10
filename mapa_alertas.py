#!/usr/bin/env python3
"""
Genera un mapa interactivo HTML con las alertas neuralgicas recopiladas.
Usa el archivo JSON más reciente en output/ o el archivo especificado.
"""

import json
import sys
from pathlib import Path
from typing import Optional

import folium
from folium.plugins import MarkerCluster

# Centro de México
MEXICO_CENTER = [23.6, -102.5]
ZOOM_START = 5

# Colores por tipo de alerta (para diferenciar visualmente)
ALERT_COLORS = {
    "default": "red",
    "incendio": "orange",
    "inundación": "blue",
    "sismo": "purple",
    "accidente": "darkred",
    "seguridad": "darkblue",
}


def get_color_for_alert(alert: dict) -> str:
    """Asigna color según el status de la alerta: PAST=gris, ACTIVE=azul."""
    status = (alert.get("status") or "").upper()
    if status == "PAST":
        return "gray"
    if status == "ACTIVE":
        return "blue"
    # Fallback: tipo de alerta para otros status
    alert_type = (alert.get("alertType") or {}).get("name", "").lower()
    for key, color in ALERT_COLORS.items():
        if key != "default" and key in alert_type:
            return color
    return ALERT_COLORS["default"]


def get_status_color(status: str) -> str:
    """Color del texto según status: PAST=gris, ACTIVE=azul."""
    s = (status or "").upper()
    if s == "PAST":
        return "#6b7280"  # gray
    if s == "ACTIVE":
        return "#2563eb"  # blue
    return "#333"


def _escape_html(text: str) -> str:
    """Escapa caracteres HTML para evitar problemas de renderizado."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _format_description(desc: str, max_len: int = 400) -> str:
    """Formatea la descripción: escapa HTML, reemplaza saltos de línea y trunca si es necesario."""
    if not desc:
        return "Sin descripción"
    desc = desc.strip()
    if len(desc) > max_len:
        desc = desc[:max_len].rsplit(" ", 1)[0] + "..."
    desc = _escape_html(desc)
    return desc.replace("\n", "<br>")


def _format_status(status: str) -> str:
    """Traduce el status a español."""
    s = (status or "").upper()
    if s == "PAST":
        return "Pasada"
    if s == "ACTIVE":
        return "Activa"
    return status or "N/A"


def _format_alert_type(alert_type: str) -> str:
    """Capitaliza el tipo de alerta."""
    if not alert_type or alert_type == "N/A":
        return "N/A"
    return alert_type.strip().capitalize()


def create_popup_html(alert: dict) -> str:
    """Genera HTML para el popup del marcador con mejor presentación."""
    title = _escape_html(alert.get("title") or "Sin título")
    description = _format_description(alert.get("description") or "")

    alert_type = _format_alert_type((alert.get("alertType") or {}).get("name") or "")
    status = _format_status(alert.get("status") or "")
    status_color = get_status_color(alert.get("status") or "")

    # Badge para indicar si hay fotos
    has_photos = bool(alert.get("photos") and len(alert.get("photos", [])) > 0)

    return f"""
    <div style="min-width: 200px; max-width: 380px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
        <div style="border-bottom: 1px solid #e5e7eb; padding-bottom: 10px; margin-bottom: 10px;">
            <h4 style="margin: 0; font-size: 1em; font-weight: 600; color: #111827; line-height: 1.35;">{title}</h4>
            <div style="display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px;">
                <span style="background: #f3f4f6; color: #374151; padding: 2px 8px; border-radius: 4px; font-size: 0.75em; font-weight: 500;">{alert_type}</span>
                <span style="background: {status_color}22; color: {status_color}; padding: 2px 8px; border-radius: 4px; font-size: 0.75em; font-weight: 600;">{status}</span>
                {f'<span style="background: #dbeafe; color: #1d4ed8; padding: 2px 8px; border-radius: 4px; font-size: 0.75em;">📷 Fotos</span>' if has_photos else ''}
            </div>
        </div>
        <p style="margin: 0; font-size: 0.85em; color: #4b5563; line-height: 1.5;">{description}</p>
    </div>
    """


def load_alerts(json_path: Path) -> list:
    """Carga alertas desde un archivo JSON."""
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else [data]


def find_latest_alerts_file() -> Optional[Path]:
    """Busca el archivo de alertas más reciente en output/."""
    output_dir = Path(__file__).parent / "output"
    if not output_dir.exists():
        return None
    files = list(output_dir.glob("alertas_mexico_*.json"))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def main():
    if len(sys.argv) > 1:
        json_path = Path(sys.argv[1])
        if not json_path.exists():
            print(f"Error: No existe el archivo {json_path}")
            sys.exit(1)
    else:
        json_path = find_latest_alerts_file()
        if not json_path:
            print("Error: No hay archivos de alertas en output/")
            print("Ejecuta primero: python3 scrape_aliado_mexico.py")
            sys.exit(1)

    print(f"Cargando alertas desde: {json_path}")
    alerts = load_alerts(json_path)

    # Filtrar alertas con coordenadas válidas
    valid_alerts = [
        a for a in alerts
        if a.get("latlon") and a["latlon"].get("lat") is not None and a["latlon"].get("lon") is not None
    ]
    excluded = len(alerts) - len(valid_alerts)

    if not valid_alerts:
        print("No hay alertas con coordenadas válidas para mostrar en el mapa.")
        sys.exit(1)

    print(f"Mostrando {len(valid_alerts)} alertas en el mapa")
    if excluded > 0:
        print(f"(Se excluyeron {excluded} sin coordenadas)")

    # Crear mapa centrado en México
    m = folium.Map(
        location=MEXICO_CENTER,
        zoom_start=ZOOM_START,
        tiles="CartoDB positron",
        control_scale=True,
    )

    # Agrupar marcadores (zoom en los círculos con números para ver los individuales)
    marker_cluster = MarkerCluster(
        name="Alertas",
        options={"maxClusterRadius": 80, "spiderfyOnMaxZoom": True},
    ).add_to(m)

    bounds = []
    for alert in valid_alerts:
        lat = float(alert["latlon"]["lat"])
        lon = float(alert["latlon"]["lon"])
        bounds.append([lat, lon])
        color = get_color_for_alert(alert)
        popup_html = create_popup_html(alert)

        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=400, parse_html=True),
            tooltip=alert.get("title") or "Ver detalles",
            icon=folium.Icon(color=color, icon="info-sign"),
        ).add_to(marker_cluster)

    # Ajustar vista para que todas las alertas queden visibles
    if bounds:
        m.fit_bounds(bounds, padding=[30, 30])

    # Añadir control de capas
    folium.LayerControl().add_to(m)

    # Guardar mapa
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "mapa_alertas.html"
    m.save(str(output_file))

    print(f"Mapa guardado en: {output_file}")
    print("Abre el archivo en tu navegador para ver las alertas.")
    if len(valid_alerts) > 20:
        print("Tip: Los círculos con números son grupos. Haz zoom en ellos para ver cada alerta.")


if __name__ == "__main__":
    main()
