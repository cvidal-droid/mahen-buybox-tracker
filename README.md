# Buy Box Tracker — Mahen

Monitorización automática de la Buy Box para los 45 ASINs de Mahen en Amazon.es.
Comprobación cada **30 minutos** vía GitHub Actions. Resumen por email cada mañana a las 9h.

---

## Estructura de archivos

```
buybox-tracker/
├── asins_config.json          ← Lista de 45 ASINs + configuración email
├── scraper.py                 ← Script de comprobación (mejorado)
├── email_digest.py            ← Script de email diario
├── requirements.txt
├── index.html                 ← Dashboard (publicar con GitHub Pages)
├── data/
│   ├── current_status.json    ← Estado actual (generado por scraper)
│   └── history.json           ← Histórico de cambios (nunca se borra)
└── .github/
    └── workflows/
        └── buybox-check.yml   ← Automatización
```

---

## Configuración paso a paso

### 1. Crear el repositorio en GitHub

1. Ve a [github.com](https://github.com) e inicia sesión (o crea cuenta)
2. Haz clic en **New repository**
3. Nombre: `mahen-buybox-tracker`
4. Visibilidad: **Public** (necesario para GitHub Pages gratis)
5. Haz clic en **Create repository**
6. Sube todos estos archivos al repo (arrastra y suelta o usa GitHub Desktop)

### 2. Activar GitHub Pages (dashboard)

1. En el repo, ve a **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: `main`, carpeta: `/ (root)`
4. Guarda. En unos minutos tendrás el dashboard en:
   `https://TU_USUARIO.github.io/mahen-buybox-tracker/`

### 3. Configurar el email (Gmail recomendado)

**Obtener contraseña de aplicación de Gmail:**
1. Ve a [myaccount.google.com](https://myaccount.google.com)
2. Seguridad → Verificación en 2 pasos (actívala si no está)
3. Seguridad → Contraseñas de aplicación
4. Crea una nueva: "Buy Box Tracker"
5. Copia la contraseña de 16 caracteres

**Añadir los Secrets en GitHub:**
1. En tu repo, ve a **Settings → Secrets and variables → Actions**
2. Haz clic en **New repository secret** para cada uno:

| Secret         | Valor                                      |
|----------------|--------------------------------------------|
| `SMTP_HOST`    | `smtp.gmail.com`                           |
| `SMTP_PORT`    | `587`                                      |
| `SMTP_USER`    | tu cuenta Gmail (ej: tucuenta@gmail.com)   |
| `SMTP_PASSWORD`| la contraseña de 16 caracteres de arriba   |
| `EMAIL_FROM`   | tu cuenta Gmail                            |
| `EMAIL_TO`     | cvidal@roicos.com                          |

### 4. Activar los Actions

1. En el repo, ve a la pestaña **Actions**
2. Si aparece un aviso de "Workflows disabled", haz clic en **Enable**
3. El scraper empezará a correr automáticamente en los próximos 30 min
4. Para probarlo ahora: **Actions → Buy Box Check → Run workflow**

---

## Funcionamiento

- **Cada 30 min**: `scraper.py` comprueba todos los ASINs y guarda cambios en `data/`
- **Cada día a las 9:00h**: `email_digest.py` envía un resumen a cvidal@roicos.com
- El histórico en `data/history.json` **nunca se borra** — acumula todos los cambios
- El dashboard (`index.html`) lee los JSON en tiempo real cuando se abre

## Leer el dashboard

- **Verde ✅** → Tienes la Buy Box (Amazon.es)
- **Rojo ❌** → Perdiste la Buy Box (aparece quién la tiene)
- **Ámbar ⚠️** → Sin stock
- **Franja de color** en cada tarjeta → historial visual del ASIN

## Nota sobre "Amazon EU S.a.r.L."

En cuentas vendor, tanto "Amazon.es" como "Amazon EU S.a.r.L." son entidades de Amazon
que venden tu inventario — ambas cuentan como Buy Box ganada (verde ✅).
La pérdida real es únicamente cuando gana un vendedor **tercero** ajeno a Amazon.
