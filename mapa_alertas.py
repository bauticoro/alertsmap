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


def _format_description(desc: str, max_len: int = 450) -> str:
    """Formatea la descripción como texto fluido y legible."""
    if not desc:
        return ""
    lines = [ln.strip() for ln in desc.strip().split("\n") if ln.strip()]
    if not lines:
        return ""

    location_parts = []
    tip_parts = []
    body_parts = []
    total_len = 0

    for line in lines:
        if total_len >= max_len:
            break
        escaped = _escape_html(line)
        if line.startswith("📍"):
            location_parts.append(escaped)
        elif line.startswith("✅"):
            tip_parts.append(escaped)
        else:
            body_parts.append(escaped)
        total_len += len(line) + 1

    # Un solo párrafo fluido, sin bloques rígidos
    chunks = []
    if location_parts:
        chunks.append(" ".join(location_parts))
    if body_parts:
        chunks.append(" ".join(body_parts))
    if tip_parts:
        chunks.append("Consejo: " + " ".join(t.replace("✅", "").strip() for t in tip_parts))

    text = " ".join(chunks)
    if not text:
        return ""
    return text


def _format_status_natural(status: str) -> str:
    """Status en lenguaje natural."""
    s = (status or "").upper()
    if s == "PAST":
        return "finalizada"
    if s == "ACTIVE":
        return "vigente"
    return ""


def _format_alert_type_natural(alert_type: str) -> str:
    """Tipo de alerta en lenguaje natural."""
    if not alert_type:
        return ""
    t = alert_type.strip().lower()
    if t == "vial":
        return "Alerta vial"
    if t == "general":
        return "Alerta general"
    return f"Alerta {t}"


ACCENT_HEX = {
    "red": "#ef4444",
    "orange": "#f97316",
    "blue": "#3b82f6",
    "purple": "#8b5cf6",
    "darkred": "#b91c1c",
    "darkblue": "#1e40af",
    "gray": "#6b7280",
}


def create_popup_html(alert: dict) -> str:
    """Genera HTML para el popup: diseño moderno tipo card con badges y acento de color."""
    title = _escape_html(alert.get("title") or "Sin título")
    description = _format_description(alert.get("description") or "")
    if not description:
        description = "Sin más detalles."

    alert_type = (alert.get("alertType") or {}).get("name") or ""
    status = _format_status_natural(alert.get("status") or "")
    is_active = (alert.get("status") or "").upper() == "ACTIVE"
    has_photos = bool(alert.get("photos") and len(alert.get("photos", [])) > 0)

    accent_color = get_color_for_alert(alert)
    accent_hex = ACCENT_HEX.get(accent_color, "#ef4444")

    type_label = _format_alert_type_natural(alert_type)
    status_badge = ""
    if status:
        bg = "rgba(34,197,94,0.15)" if is_active else "rgba(107,114,128,0.15)"
        fg = "#16a34a" if is_active else "#6b7280"
        status_badge = f'<span style="display:inline-block;padding:3px 8px;border-radius:6px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;background:{bg};color:{fg};">{status}</span>'
    type_badge = ""
    if type_label:
        type_badge = f'<span style="display:inline-block;padding:3px 8px;border-radius:6px;font-size:11px;font-weight:600;background:rgba(59,130,246,0.12);color:#2563eb;">{type_label}</span>'
    badges = " ".join(b for b in [type_badge, status_badge] if b)

    photos_html = ' <span style="display:inline-flex;align-items:center;gap:4px;color:#64748b;font-size:12px;">📷 Fotos adjuntas</span>' if has_photos else ""

    return f"""
    <div style="min-width:260px;max-width:380px;font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
        <div style="height:4px;background:{accent_hex};"></div>
        <div style="padding:16px 18px;">
            <h3 style="margin:0 0 12px;font-size:15px;font-weight:700;line-height:1.35;color:#0f172a;letter-spacing:-0.02em;">{title}</h3>
            {f'<div style="margin-bottom:12px;display:flex;flex-wrap:wrap;gap:6px;">{badges}</div>' if badges else ''}
            <p style="margin:0;font-size:13px;line-height:1.55;color:#475569;">{description}{photos_html}</p>
        </div>
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
        tiles="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        attr="© CARTO",
        control_scale=True,
    )

    # Favicon y título de Chofex (embebido porque chofex.com/favicon.png falla a veces)
    favicon_path = Path(__file__).parent / "web" / "favicon.png"
    if favicon_path.exists():
        import base64
        with open(favicon_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        m.get_root().header.add_child(
            folium.Element(f'<link rel="icon" type="image/png" href="data:image/png;base64,{b64}">')
        )
    m.get_root().header.add_child(folium.Element("<title>Chofex · Mapa de alertas</title>"))

    # Estilos modernos para los popups
    popup_css = """
    <style>
    .leaflet-popup-content { margin: 0; }
    .leaflet-popup-content-wrapper { border-radius: 12px; overflow: hidden; box-shadow: 0 10px 40px rgba(0,0,0,0.15), 0 2px 8px rgba(0,0,0,0.08); }
    .leaflet-popup-tip { box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
    </style>
    """
    m.get_root().header.add_child(folium.Element(popup_css))

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

    # Ocultar tooltip al abrir popup; rebind al cerrar (evitar preview + tarjeta a la vez)
    map_name = m.get_name()
    close_tooltip_script = f"""
(function() {{
  var map = {map_name};
  if (map) {{
    map.on('popupopen', function(e) {{
      var marker = e.popup && e.popup._source;
      if (marker) {{
        var tooltip = marker.getTooltip && marker.getTooltip();
        if (tooltip) {{
          marker._storedTooltipContent = (tooltip.options && tooltip.options.content) || tooltip._content || '';
          marker.unbindTooltip && marker.unbindTooltip();
        }}
      }}
    }});
    map.on('popupclose', function(e) {{
      var marker = e.popup && e.popup._source;
      if (marker && marker._storedTooltipContent) {{
        marker.bindTooltip(marker._storedTooltipContent, {{ permanent: false }});
        marker._storedTooltipContent = null;
      }}
    }});
  }}
}})();
"""
    m.get_root().script.add_child(folium.Element(close_tooltip_script))

    # Guardar mapa
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "mapa_alertas.html"
    m.save(str(output_file))

    # Copiar JSON a web/ y generar index.html con data embebida (evita fetch en Network)
    web_dir = Path(__file__).parent / "web"
    if web_dir.exists():
        import shutil
        from build_web import build_web

        web_json = web_dir / "alertas.json"
        shutil.copy2(json_path, web_json)
        print(f"JSON copiado a {web_json} (para Vercel)")

        template_path = web_dir / "index.template.html"
        output_path = web_dir / "index.html"
        if template_path.exists():
            build_web(web_json, template_path, output_path)

    print(f"Mapa guardado en: {output_file}")
    print("Abre el archivo en tu navegador para ver las alertas.")
    if len(valid_alerts) > 20:
        print("Tip: Los círculos con números son grupos. Haz zoom en ellos para ver cada alerta.")


if __name__ == "__main__":
    main()
