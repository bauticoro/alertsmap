#!/usr/bin/env python3
"""
Genera index.html con las alertas embebidas (base64) para que no aparezcan
como petición separada en la pestaña Network de DevTools.
"""

import base64
import json
import sys
from pathlib import Path


def build_web(alertas_path: Path, template_path: Path, output_path: Path) -> None:
    """Lee alertas.json, las codifica en base64 y las incrusta en el HTML."""
    with open(alertas_path, encoding="utf-8") as f:
        data = json.load(f)
    json_str = json.dumps(data, ensure_ascii=False)
    b64 = base64.b64encode(json_str.encode("utf-8")).decode("ascii")

    with open(template_path, encoding="utf-8") as f:
        html = f.read()

    if "{{__ALERTS_B64__}}" not in html:
        print("Error: Placeholder {{__ALERTS_B64__}} no encontrado en la plantilla")
        sys.exit(1)

    html = html.replace("{{__ALERTS_B64__}}", b64)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Build OK: {output_path} (alertas embebidas, sin fetch a alertas.json)")


def main():
    script_dir = Path(__file__).parent
    web_dir = script_dir / "web"
    alertas_path = web_dir / "alertas.json"
    template_path = web_dir / "index.template.html"
    output_path = web_dir / "index.html"

    if not alertas_path.exists():
        print(f"Error: No existe {alertas_path}")
        print("Ejecuta primero: python3 mapa_alertas.py")
        sys.exit(1)

    build_web(alertas_path, template_path, output_path)


if __name__ == "__main__":
    main()
