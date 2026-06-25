"""
email_digest.py — Resumen diario de Buy Box para MAHEN
-------------------------------------------------------
Lee current_status.json e history.json y envía un email HTML
con el estado actual y los cambios de las últimas 24 horas.

Variables de entorno necesarias (configurar en GitHub Actions Secrets):
  SMTP_HOST     → smtp.gmail.com  (o tu servidor)
  SMTP_PORT     → 587
  SMTP_USER     → tu_cuenta@gmail.com
  SMTP_PASSWORD → tu contraseña de aplicación de Gmail
  EMAIL_FROM    → tu_cuenta@gmail.com
  EMAIL_TO      → cvidal@roicos.com  (o tomar del config)

Uso:
    python email_digest.py
"""

import json
import os
import smtplib
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "asins_config.json"
DATA_DIR = BASE_DIR / "data"
HISTORY_FILE = DATA_DIR / "history.json"
CURRENT_FILE = DATA_DIR / "current_status.json"


def load_json(path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def status_emoji(entry):
    if entry.get("in_stock") is False:
        return "⚠️"
    if entry.get("has_buybox_amazon"):
        return "✅"
    return "❌"


def status_label(entry):
    if entry.get("last_error"):
        return f"Error de scraping"
    if entry.get("in_stock") is False:
        return "Sin stock"
    if entry.get("has_buybox_amazon"):
        seller = entry.get("seller_name", "Amazon")
        return f"BB ganada · {seller}"
    seller = entry.get("seller_name") or "desconocido"
    return f"BB perdida → {seller}"


def event_label(event):
    return {"won": "✅ Recuperada", "lost": "❌ Perdida", "out_of_stock": "⚠️ Sin stock"}.get(event, event)


def build_html(current, history, config):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    # Últimas 24h de cambios
    recent = [
        e for e in history
        if datetime.fromisoformat(e["timestamp"]) >= cutoff
    ]
    recent.sort(key=lambda e: e["timestamp"], reverse=True)

    # Estadísticas del estado actual
    total = len(current)
    won = sum(1 for v in current.values() if v.get("has_buybox_amazon") and v.get("in_stock") is not False)
    lost = sum(1 for v in current.values() if not v.get("has_buybox_amazon") and v.get("in_stock") is not False and not v.get("last_error"))
    no_stock = sum(1 for v in current.values() if v.get("in_stock") is False)
    errors = sum(1 for v in current.values() if v.get("last_error"))

    # Título del email
    alert_icon = "🚨" if lost > 0 or no_stock > 0 else "✅"
    date_str = now.strftime("%d/%m/%Y")
    subject = f"{alert_icon} Mahen Buy Box — {date_str} · {won}/{total} ganadas"

    # Construir tabla de productos perdidos (para destacar)
    lost_rows = ""
    for asin, data in sorted(current.items(), key=lambda x: x[1].get("label", "")):
        if not data.get("has_buybox_amazon") and data.get("in_stock") is not False and not data.get("last_error"):
            seller = data.get("seller_name") or "desconocido"
            price = data.get("price") or "—"
            label = data.get("label", asin)
            lost_rows += f"""
            <tr>
              <td style="padding:8px 12px; border-bottom:1px solid #f0e0e0;">{label}</td>
              <td style="padding:8px 12px; border-bottom:1px solid #f0e0e0; font-family:monospace; font-size:12px; color:#888;">{asin}</td>
              <td style="padding:8px 12px; border-bottom:1px solid #f0e0e0; color:#c0392b;">{seller}</td>
              <td style="padding:8px 12px; border-bottom:1px solid #f0e0e0; text-align:right;">{price}</td>
            </tr>"""

    # Tabla de cambios recientes
    change_rows = ""
    for ev in recent[:20]:
        ts = datetime.fromisoformat(ev["timestamp"]).strftime("%H:%M")
        color = {"won": "#27ae60", "lost": "#c0392b", "out_of_stock": "#e67e22"}.get(ev.get("event"), "#666")
        change_rows += f"""
            <tr>
              <td style="padding:6px 12px; border-bottom:1px solid #eee; color:#888; font-size:12px; white-space:nowrap;">{ts}</td>
              <td style="padding:6px 12px; border-bottom:1px solid #eee;">{ev.get('label', ev['asin'])}</td>
              <td style="padding:6px 12px; border-bottom:1px solid #eee; color:{color}; font-weight:600;">{event_label(ev.get('event', ''))}</td>
              <td style="padding:6px 12px; border-bottom:1px solid #eee; font-size:12px; color:#555;">{ev.get('seller_name') or '—'}</td>
            </tr>"""

    no_changes_msg = "" if change_rows else "<p style='color:#888; text-align:center; padding:20px 0;'>Sin cambios en las últimas 24 horas.</p>"

    html = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0; padding:0; background:#f5f7fa; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f7fa; padding:30px 0;">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff; border-radius:10px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.08);">

      <!-- Header -->
      <tr>
        <td style="background:#1a202c; padding:28px 32px;">
          <p style="margin:0; color:#a0aec0; font-size:12px; text-transform:uppercase; letter-spacing:0.08em;">Resumen diario · {date_str}</p>
          <h1 style="margin:8px 0 0; color:#ffffff; font-size:22px; font-weight:700;">Buy Box Tracker — Mahen</h1>
        </td>
      </tr>

      <!-- Chips de resumen -->
      <tr>
        <td style="padding:24px 32px 8px; background:#f8fafc; border-bottom:1px solid #e2e8f0;">
          <table cellpadding="0" cellspacing="0">
            <tr>
              <td style="padding:8px 16px; background:#e6f4ea; border-radius:100px; margin-right:8px;">
                <span style="color:#27ae60; font-weight:700; font-size:20px;">{won}</span>
                <span style="color:#27ae60; font-size:13px; margin-left:4px;">con Buy Box</span>
              </td>
              <td style="width:10px;"></td>
              <td style="padding:8px 16px; background:#fde8e8; border-radius:100px;">
                <span style="color:#c0392b; font-weight:700; font-size:20px;">{lost}</span>
                <span style="color:#c0392b; font-size:13px; margin-left:4px;">perdida{"s" if lost != 1 else ""}</span>
              </td>
              <td style="width:10px;"></td>
              {"" if no_stock == 0 else f"""<td style="padding:8px 16px; background:#fef3cd; border-radius:100px;">
                <span style="color:#e67e22; font-weight:700; font-size:20px;">{no_stock}</span>
                <span style="color:#e67e22; font-size:13px; margin-left:4px;">sin stock</span>
              </td>"""}
              {"" if errors == 0 else f"""<td style="width:10px;"></td><td style="padding:8px 16px; background:#f0f0f0; border-radius:100px;">
                <span style="color:#888; font-weight:700; font-size:20px;">{errors}</span>
                <span style="color:#888; font-size:13px; margin-left:4px;">errores</span>
              </td>"""}
            </tr>
          </table>
          <p style="margin:12px 0 0; color:#888; font-size:12px;">Total: {total} ASINs monitorizados</p>
        </td>
      </tr>

      <!-- Cambios en las últimas 24h -->
      <tr>
        <td style="padding:24px 32px 8px;">
          <h2 style="margin:0 0 14px; font-size:15px; font-weight:700; color:#1a202c;">Cambios en las últimas 24h</h2>
          {"" if not change_rows else f"""
          <table width="100%" cellpadding="0" cellspacing="0" style="font-size:13px;">
            <thead>
              <tr style="background:#f8fafc;">
                <th style="padding:6px 12px; text-align:left; color:#888; font-size:11px; font-weight:600; text-transform:uppercase; border-bottom:2px solid #e2e8f0;">Hora</th>
                <th style="padding:6px 12px; text-align:left; color:#888; font-size:11px; font-weight:600; text-transform:uppercase; border-bottom:2px solid #e2e8f0;">Producto</th>
                <th style="padding:6px 12px; text-align:left; color:#888; font-size:11px; font-weight:600; text-transform:uppercase; border-bottom:2px solid #e2e8f0;">Estado</th>
                <th style="padding:6px 12px; text-align:left; color:#888; font-size:11px; font-weight:600; text-transform:uppercase; border-bottom:2px solid #e2e8f0;">Vendedor</th>
              </tr>
            </thead>
            <tbody>{change_rows}</tbody>
          </table>"""}
          {no_changes_msg}
        </td>
      </tr>

      <!-- Productos con BB perdida ahora mismo -->
      {"" if not lost_rows else f"""
      <tr>
        <td style="padding:24px 32px 8px;">
          <h2 style="margin:0 0 14px; font-size:15px; font-weight:700; color:#c0392b;">❌ Buy Box perdida ahora mismo ({lost})</h2>
          <table width="100%" cellpadding="0" cellspacing="0" style="font-size:13px;">
            <thead>
              <tr style="background:#fff5f5;">
                <th style="padding:6px 12px; text-align:left; color:#888; font-size:11px; font-weight:600; text-transform:uppercase; border-bottom:2px solid #f0e0e0;">Producto</th>
                <th style="padding:6px 12px; text-align:left; color:#888; font-size:11px; font-weight:600; text-transform:uppercase; border-bottom:2px solid #f0e0e0;">ASIN</th>
                <th style="padding:6px 12px; text-align:left; color:#888; font-size:11px; font-weight:600; text-transform:uppercase; border-bottom:2px solid #f0e0e0;">Vendedor ganador</th>
                <th style="padding:6px 12px; text-align:right; color:#888; font-size:11px; font-weight:600; text-transform:uppercase; border-bottom:2px solid #f0e0e0;">Precio</th>
              </tr>
            </thead>
            <tbody>{lost_rows}</tbody>
          </table>
        </td>
      </tr>"""}

      <!-- Footer -->
      <tr>
        <td style="padding:24px 32px; background:#f8fafc; border-top:1px solid #e2e8f0;">
          <p style="margin:0; color:#aaa; font-size:12px;">
            Generado automáticamente · Buy Box Tracker · Mahen Amazon.es<br>
            Datos recogidos cada 30 minutos vía GitHub Actions.
          </p>
        </td>
      </tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""

    return subject, html


def send_email(subject, html_body, config):
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASSWORD")
    email_from = os.environ.get("EMAIL_FROM", smtp_user)
    email_to = os.environ.get("EMAIL_TO") or config.get("email_to", "cvidal@roicos.com")

    if not smtp_user or not smtp_pass:
        print("⚠️  SMTP_USER o SMTP_PASSWORD no configurados. Email no enviado.")
        print("   Configura los Secrets en GitHub Actions para activar el envío.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_from
    msg["To"] = email_to
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(email_from, [email_to], msg.as_bytes())

    print(f"✅ Email enviado a {email_to}")
    return True


def main():
    config = load_json(CONFIG_FILE, {})
    current = load_json(CURRENT_FILE, {})
    history = load_json(HISTORY_FILE, [])

    if not current:
        print("No hay datos en current_status.json. Ejecuta scraper.py primero.")
        return

    subject, html = build_html(current, history, config)
    print(f"Subject: {subject}")
    send_email(subject, html, config)


if __name__ == "__main__":
    main()
