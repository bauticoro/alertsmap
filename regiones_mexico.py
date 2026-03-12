#!/usr/bin/env python3
"""
Identifica la región de México a la que pertenece cada alerta.
Usa reverse geocoding (coordenadas -> estado) y mapea estado -> región.
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional, Tuple

# Regiones de México según el usuario (estado -> región principal)
# Para estados en múltiples regiones, se usa la primera ocurrencia
REGIONES = {
    # Noroeste
    "Baja California": "Noroeste",
    "Baja California Sur": "Noroeste",
    "Chihuahua": "Noroeste",
    "Durango": "Noroeste",
    "Sinaloa": "Noroeste",
    "Sonora": "Noroeste",
    # Noreste
    "Coahuila": "Noreste",
    "Nuevo León": "Noreste",
    "Tamaulipas": "Noreste",
    # Occidente
    "Colima": "Occidente",
    "Guanajuato": "Occidente",
    "Jalisco": "Occidente",
    "Michoacán": "Occidente",
    "Michoacan": "Occidente",  # sin tilde
    "Nayarit": "Occidente",
    # Oriente
    "Hidalgo": "Oriente",
    "Puebla": "Oriente",
    "Veracruz": "Oriente",
    "Tlaxcala": "Oriente",
    "San Luis Potosí": "Oriente",
    "San Luis Potosi": "Oriente",  # sin tilde
    # Centronorte
    "Aguascalientes": "Centronorte",
    "Querétaro": "Centronorte",
    "Queretaro": "Centronorte",  # sin tilde
    "Zacatecas": "Centronorte",
    # Centrosur
    "Ciudad de México": "Centrosur",
    "Mexico City": "Centrosur",
    "Distrito Federal": "Centrosur",
    "Estado de México": "Centrosur",
    "México": "Centrosur",  # puede ser EdoMex
    "Mexico": "Centrosur",
    "Guerrero": "Centrosur",
    "Morelos": "Centrosur",
    # Suroeste
    "Chiapas": "Suroeste",
    "Oaxaca": "Suroeste",
    # Sureste
    "Campeche": "Sureste",
    "Quintana Roo": "Sureste",
    "Tabasco": "Sureste",
    "Yucatán": "Sureste",
    "Yucatan": "Sureste",  # sin tilde
}

# Variaciones que aparecen en títulos/descripciones (abreviaturas, etc.)
VARIACIONES_TEXTO = {
    "cdmx": "Ciudad de México",
    "ciudad de méxico": "Ciudad de México",
    "edomex": "Estado de México",
    "edo mex": "Estado de México",
    "edo. mex": "Estado de México",
    "estado de méxico": "Estado de México",
    "hgo": "Hidalgo",
    "hidalgo": "Hidalgo",
    "querétaro": "Querétaro",
    "queretaro": "Querétaro",
    "guanajuato": "Guanajuato",
    "jalisco": "Jalisco",
    "michoacán": "Michoacán",
    "michoacan": "Michoacán",
    "sinaloa": "Sinaloa",
    "sonora": "Sonora",
    "chihuahua": "Chihuahua",
    "baja california": "Baja California",
    "nuevo león": "Nuevo León",
    "nuevo leon": "Nuevo León",
    "coahuila": "Coahuila",
    "tamaulipas": "Tamaulipas",
    "puebla": "Puebla",
    "veracruz": "Veracruz",
    "campeche": "Campeche",
    "yucatán": "Yucatán",
    "yucatan": "Yucatán",
    "quintana roo": "Quintana Roo",
    "tabasco": "Tabasco",
    "chiapas": "Chiapas",
    "oaxaca": "Oaxaca",
    "guerrero": "Guerrero",
    "morelos": "Morelos",
    "tlaxcala": "Tlaxcala",
    "san luis potosí": "San Luis Potosí",
    "san luis potosi": "San Luis Potosí",
    "aguascalientes": "Aguascalientes",
    "zacatecas": "Zacatecas",
    "durango": "Durango",
    "colima": "Colima",
    "nayarit": "Nayarit",
    "monterrey": "Nuevo León",
    "guadalajara": "Jalisco",
    "morelia": "Michoacán",
    "mazatlán": "Sinaloa",
    "mazatlan": "Sinaloa",
    "toluca": "Estado de México",
    "cuernavaca": "Morelos",
    "iguala": "Guerrero",
    "champotón": "Campeche",
    "champoton": "Campeche",
    "silao": "Guanajuato",
    "rioverde": "San Luis Potosí",
    "cerritos": "San Luis Potosí",
    "atlacomulco": "Estado de México",
    "texmelucan": "Puebla",
    "tula": "Hidalgo",
    "zacapu": "Michoacán",
    "nogales": "Sonora",
    "jiquilpan": "Michoacán",
    "uruapan": "Michoacán",
    "tehuacán": "Puebla",
    "tehuacan": "Puebla",
    "tehuantepec": "Oaxaca",
    "mitla": "Oaxaca",
    "tepic": "Nayarit",
    "puerto vallarta": "Jalisco",
    "zaragoza": "Coahuila",
    "lázaro cárdenas": "Michoacán",
    "lazaro cardenas": "Michoacán",
}


def _get_latlon(alert: dict) -> Optional[Tuple[float, float]]:
    """Extrae lat, lon de una alerta."""
    latlon = alert.get("latlon")
    if not latlon:
        return None
    lat = latlon.get("lat")
    lon = latlon.get("lon")
    if lat is None or lon is None:
        return None
    return (float(lat), float(lon))


def _es_guatemala(lat: float, lon: float) -> bool:
    """Coordenadas típicas de Guatemala (aprox)."""
    return lat < 16.5 and -92.5 < lon < -88.5


def _normalizar(texto: str) -> str:
    """Normaliza texto para búsqueda (minúsculas, sin acentos)."""
    if not texto:
        return ""
    t = texto.lower()
    for a, b in [("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n")]:
        t = t.replace(a, b)
    return t


def _buscar_estado_en_texto(texto: str) -> Optional[str]:
    """Busca menciones de estados en título/descripción. Prioriza título."""
    if not texto:
        return None
    texto_norm = _normalizar(texto)
    # Buscar primero abreviaturas explícitas (Hgo, EdoMex, S.L.P, etc.)
    abrevs = [
        ("hgo", "Hidalgo"),
        ("edo mex", "Estado de México"),
        ("edomex", "Estado de México"),
        ("s.l.p", "San Luis Potosí"),
        ("cdmx", "Ciudad de México"),
    ]
    for abrev, estado in abrevs:
        if abrev in texto_norm:
            return estado
    # Luego ciudades/lugares más específicos (variaciones ya normalizadas)
    for variacion, estado in sorted(VARIACIONES_TEXTO.items(), key=lambda x: -len(x[0])):
        if _normalizar(variacion) in texto_norm:
            return estado
    return None


def _estado_a_region(estado: str) -> str:
    """Mapea nombre de estado a región."""
    return REGIONES.get(estado, "Desconocida")


def identificar_region(alert: dict, use_reverse_geocode: bool = True) -> dict:
    """
    Identifica la región de una alerta.
    Retorna: {"region": str, "estado": str|None, "metodo": str, "es_guatemala": bool}
    """
    latlon = _get_latlon(alert)
    title = alert.get("title", "")
    desc = alert.get("description", "")
    texto = f"{title} {desc}"

    # 1. Si tiene coordenadas en Guatemala
    if latlon:
        lat, lon = latlon
        if _es_guatemala(lat, lon):
            return {
                "region": "Guatemala (no aplica)",
                "estado": None,
                "metodo": "coordenadas",
                "es_guatemala": True,
            }

    # 2. Buscar estado en texto
    estado_texto = _buscar_estado_en_texto(texto)
    if estado_texto:
        return {
            "region": _estado_a_region(estado_texto),
            "estado": estado_texto,
            "metodo": "texto",
            "es_guatemala": False,
        }

    # 3. Reverse geocode si hay coordenadas
    if latlon and use_reverse_geocode:
        try:
            import reverse_geocode
            lat, lon = latlon
            result = reverse_geocode.get((lat, lon), min_population=1000)
            if result and result.get("country_code") == "MX":
                state = result.get("state", "")
                if state:
                    region = _estado_a_region(state)
                    if region != "Desconocida":
                        return {
                            "region": region,
                            "estado": state,
                            "metodo": "reverse_geocode",
                            "es_guatemala": False,
                        }
            elif result and result.get("country_code") == "GT":
                return {
                    "region": "Guatemala (no aplica)",
                    "estado": None,
                    "metodo": "reverse_geocode",
                    "es_guatemala": True,
                }
        except ImportError:
            pass
        except Exception:
            pass

    return {
        "region": "Desconocida",
        "estado": None,
        "metodo": "ninguno",
        "es_guatemala": False,
    }


def main():
    script_dir = Path(__file__).parent
    output_dir = script_dir / "output"
    json_files = sorted(
        [p for p in output_dir.glob("alertas_mexico_*.json") if "_con_regiones" not in p.name],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not json_files:
        print("No se encontraron archivos alertas_mexico_*.json en output/")
        sys.exit(1)

    path = json_files[0]
    print(f"Leyendo: {path.name}\n")

    with open(path, encoding="utf-8") as f:
        alertas = json.load(f)

    # Intentar reverse_geocode solo si está instalado
    try:
        import reverse_geocode
        use_rg = True
    except ImportError:
        use_rg = False
        print("(reverse-geocode no instalado; usando solo texto. Instala con: pip install reverse-geocode)\n")

    resultados = []
    for i, alerta in enumerate(alertas):
        info = identificar_region(alerta, use_reverse_geocode=use_rg)
        info["id"] = alerta.get("id", str(i))
        info["title"] = (alerta.get("title") or "")[:60]
        resultados.append(info)

    # Resumen por región
    por_region = {}
    for r in resultados:
        reg = r["region"]
        por_region[reg] = por_region.get(reg, 0) + 1

    print("=" * 70)
    print("RESUMEN POR REGIÓN")
    print("=" * 70)
    for reg in sorted(por_region.keys(), key=lambda x: (-por_region[x], x)):
        print(f"  {reg}: {por_region[reg]} alertas")

    print("\n" + "=" * 70)
    print("DETALLE POR ALERTA (primeras 30)")
    print("=" * 70)
    for r in resultados[:30]:
        estado_str = f" ({r['estado']})" if r["estado"] else ""
        print(f"  [{r['region']}]{estado_str} | {r['metodo']} | {r['title'][:50]}...")

    # Guardar JSON con regiones
    out_path = path.parent / f"{path.stem}_con_regiones.json"
    output_data = []
    for alerta, res in zip(alertas, resultados):
        item = {**alerta, "region": res["region"], "estado": res["estado"], "region_metodo": res["metodo"]}
        output_data.append(item)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"\nGuardado: {out_path}")


if __name__ == "__main__":
    main()
