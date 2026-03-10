# Mapa de Alertas - Deploy en Vercel

## Desplegar

1. **Conecta tu repo** en [vercel.com](https://vercel.com) (Import Git Repository).

2. **Configura el Root Directory**: En **Project Settings → General → Root Directory** pon `web` y guarda. Así Vercel usará esta carpeta como raíz.

3. **Deploy**: Cada push a tu rama principal hará deploy automático.

### Alternativa con CLI

```bash
npm i -g vercel
cd "Scraper de Aliado"
vercel
```

Cuando pregunte por el Root Directory, indica `web`.

## Actualizar datos

Cada vez que ejecutes el scraper y generes el mapa:

```bash
python3 scrape_aliado_mexico.py
python3 mapa_alertas.py
```

El script `mapa_alertas.py` copia automáticamente el JSON a `web/alertas.json`. Luego haz commit y push, o vuelve a desplegar con `vercel --prod`.
