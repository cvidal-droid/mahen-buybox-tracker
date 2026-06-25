"""
Amazon Buy Box Tracker — scraper.py v2
---------------------------------------
Mejoras respecto a v1:
  - Rotación de User-Agents para reducir bloqueos
  - Múltiples selectores CSS con fallback (Amazon cambia el HTML sin avisar)
  - Retries con backoff exponencial en errores HTTP
  - Captura del vendedor ganador (no solo si es Amazon)
  - Captura del precio ganador para comparar
  - Registro del motivo de pérdida: tercero / Amazon-EU / sin stock / error
  - Logging detallado para depuración en GitHub Actions

Uso:
    python scraper.py

Compatible con el workflow .github/workflows/buybox-check.yml
"""

import json
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------- Rutas ----------
BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "asins_config.json"
DATA_DIR = BASE_DIR / "data"
HISTORY_FILE = DATA_DIR / "history.json"
CURRENT_FILE = DATA_DIR / "current_status.json"

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------- User-Agents rotatorios ----------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]

# Selectores para el vendedor de la Buy Box (en orden de fiabilidad)
SELLER_SELECTORS = [
    "#sellerProfileTriggerId",
    "#merchant-info a",
    "#merchant-info",
    ".tabular-buybox-text[tabular-attribute-name='Vendido por'] span",
    ".tabular-buybox-text[tabular-attribute-name='Sold by'] span",
    "#tabular-buybox-container .tabular-buybox-text:last-of-type span",
    "#soldByThirdParty",
    "#snsAccordionRowMiddle .tabular-buybox-text span",
]

# Selectores para el precio (orientativo)
PRICE_SELECTORS = [
    "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
    ".a-price.priceToPay .a-offscreen",
    "#corePrice_feature_div .a-price .a-offscreen",
    "#price_inside_buybox",
    "#sns-base-price",
]


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_json(path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0",
    }


def fetch_page(url, retries=3):
    """Descarga la página con reintentos y backoff exponencial."""
    session = requests.Session()
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, headers=_get_headers(), timeout=20)
            if resp.status_code == 503:
                log.warning(f"503 recibido (intento {attempt}/{retries}), esperando...")
                time.sleep(2 ** attempt + random.uniform(1, 3))
                continue
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.Timeout:
            log.warning(f"Timeout en intento {attempt}/{retries} para {url}")
            time.sleep(2 ** attempt)
        except requests.exceptions.HTTPError as e:
            log.warning(f"HTTP {e.response.status_code} en intento {attempt}/{retries}")
            time.sleep(2 ** attempt)
        except Exception as e:
            log.error(f"Error inesperado: {e}")
            time.sleep(2 ** attempt)
    return None


def classify_seller(seller_name):
    """
    Clasifica al vendedor de la Buy Box:
      'amazon_es'  → Amazon.es (lo que queremos como vendor)
      'amazon_eu'  → Amazon EU S.a.r.L. (entidad EU de Amazon, puede ser problema)
      'amazon_any' → Otra entidad de Amazon
      'third_party'→ Vendedor externo (pérdida confirmada)
      'unknown'    → No se pudo leer
    """
    if not seller_name:
        return "unknown"
    lower = seller_name.lower()
    if "amazon.es" in lower:
        return "amazon_es"
    if "amazon eu" in lower or "amazon eu s.a.r.l" in lower:
        return "amazon_eu"
    if "amazon" in lower:
        return "amazon_any"
    return "third_party"


def fetch_buybox_status(asin, domain="amazon.es"):
    """
    Obtiene el estado de la Buy Box para un ASIN.
    Devuelve un dict con:
      seller_name      : nombre visible del vendedor
      seller_type      : amazon_es | amazon_eu | amazon_any | third_party | unknown
      has_buybox_amazon: True si cualquier entidad Amazon tiene la BB
      in_stock         : bool
      price            : str | None
      error            : str (solo si falló la petición)
    """
    url = f"https://www.{domain}/dp/{asin}"
    html = fetch_page(url)

    if html is None:
        return {"error": "No se pudo descargar la página tras reintentos"}

    soup = BeautifulSoup(html, "lxml")

    # Comprobación básica de que es una página de producto real
    if not soup.select_one("#dp") and not soup.select_one("#ppd"):
        # Amazon devolvió CAPTCHA o página de error
        if soup.find(string=lambda t: t and "robot" in t.lower()):
            return {"error": "CAPTCHA detectado"}
        # Podría ser un ASIN inexistente o redirigido
        log.warning(f"ASIN {asin}: página sin estructura esperada")

    # ---- Vendedor de la Buy Box ----
    seller_name = None
    for selector in SELLER_SELECTORS:
        tag = soup.select_one(selector)
        if tag:
            text = tag.get_text(strip=True)
            if text and len(text) > 1:
                seller_name = text
                log.debug(f"ASIN {asin}: vendedor '{seller_name}' vía selector '{selector}'")
                break

    # Fallback: buscar texto "Vendido por" en el buybox
    if not seller_name:
        for tag in soup.select(".a-section"):
            text = tag.get_text()
            if "vendido por" in text.lower() or "sold by" in text.lower():
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                for i, line in enumerate(lines):
                    if "vendido por" in line.lower() or "sold by" in line.lower():
                        if i + 1 < len(lines):
                            seller_name = lines[i + 1]
                            break
                if seller_name:
                    break

    seller_type = classify_seller(seller_name)

    # ---- Disponibilidad ----
    in_stock = True
    avail = soup.select_one("#availability span")
    if avail:
        avail_text = avail.get_text(strip=True).lower()
        unavailable_phrases = [
            "no disponible", "unavailable", "agotado",
            "no se puede", "temporalmente", "currently unavailable",
            "out of stock",
        ]
        if any(p in avail_text for p in unavailable_phrases):
            in_stock = False
    elif soup.select_one("#outOfStock") or soup.select_one("#exports_desktop_outOfStock_feature_div"):
        in_stock = False

    # Si no hay botón de añadir al carrito, probablemente sin stock o sin BB
    if in_stock and not soup.select_one("#add-to-cart-button") and not soup.select_one("#buy-now-button"):
        # No lo marcamos como sin stock aquí porque puede ser un problema de parseo
        log.debug(f"ASIN {asin}: sin botón AddToCart — posible problema de scraping o sin stock real")

    # ---- Precio ----
    price = None
    for selector in PRICE_SELECTORS:
        tag = soup.select_one(selector)
        if tag:
            price = tag.get_text(strip=True)
            break

    has_buybox_amazon = seller_type in ("amazon_es", "amazon_eu", "amazon_any")

    return {
        "seller_name": seller_name,
        "seller_type": seller_type,
        "has_buybox_amazon": has_buybox_amazon,
        "in_stock": in_stock,
        "price": price,
    }


def check_all():
    config = load_config()
    history = load_json(HISTORY_FILE, [])
    current = load_json(CURRENT_FILE, {})
    now = datetime.now(timezone.utc).isoformat()

    errors = 0
    changes = 0

    for item in config["asins"]:
        asin = item["asin"]
        label = item.get("label", asin)
        domain = item.get("domain", config.get("domain", "amazon.es"))

        log.info(f"Comprobando {asin} ({label})...")
        status = fetch_buybox_status(asin, domain=domain)
        previous = current.get(asin, {})

        if "error" in status:
            log.error(f"  → ERROR: {status['error']}")
            errors += 1
            # Guardamos el error en current pero NO tocamos el historial
            current[asin] = {
                **previous,
                "label": label,
                "last_checked": now,
                "last_error": status["error"],
            }
            time.sleep(random.uniform(3, 7))
            continue

        # ¿Cambió algo relevante?
        changed = (
            asin not in current
            or previous.get("seller_name") != status.get("seller_name")
            or previous.get("in_stock") != status.get("in_stock")
        )

        if changed:
            changes += 1
            event_type = (
                "out_of_stock" if not status["in_stock"]
                else "won" if status["has_buybox_amazon"]
                else "lost"
            )
            history.append({
                "timestamp": now,
                "asin": asin,
                "label": label,
                "event": event_type,
                **status,
            })
            log.info(f"  → CAMBIO ({event_type}): vendedor='{status['seller_name']}', "
                     f"in_stock={status['in_stock']}, precio={status['price']}")
        else:
            log.info(f"  → Sin cambios. BB={'✓' if status['has_buybox_amazon'] else '✗'}, "
                     f"vendedor='{status['seller_name']}'")

        current[asin] = {**status, "label": label, "last_checked": now}

        # Pausa cortesía entre peticiones
        time.sleep(random.uniform(3, 6))

    save_json(HISTORY_FILE, history)
    save_json(CURRENT_FILE, current)

    log.info(
        f"\n{'='*50}\n"
        f"Resumen: {len(config['asins'])} ASINs | "
        f"{changes} cambios | {errors} errores | "
        f"{len(history)} eventos totales en histórico\n"
        f"{'='*50}"
    )


if __name__ == "__main__":
    check_all()
