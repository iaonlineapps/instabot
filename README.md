# InstaBot

Bot de Telegram que publica en tu Instagram lo que le mandas. / *Telegram bot that posts to your Instagram whatever you send it.*

- 📷 Una foto → post. / *One photo → post.*
- 🖼️ Varias fotos o vídeos a la vez (hasta 10) → carrusel. / *Several at once (up to 10) → carousel.*
- 🎬 Un vídeo → Reel. / *One video → Reel.*
- El pie de foto es el texto del post. Antes de publicar enseña una vista previa con ✅ Publicar, ✏️ Cambiar texto y ❌ Cancelar (o publica directo con `/auto`).
- Solo obedece a la primera persona que le escribe `/start` (su dueño).
- Usa la API oficial de Instagram (*Instagram API with Instagram Login*): cuenta profesional (Empresa o Creador), sin página de Facebook. La llave dura 60 días y el bot la renueva solo.
- Las fotos se ajustan solas a lo que pide Instagram (JPEG, entre 4:5 y 1,91:1).
- Español e inglés (`/idioma`).

## Cómo funciona

Instagram no deja subir el archivo directamente: pide una **dirección pública** de donde bajarlo. El bot sirve cada archivo un rato en `https://TU-DOMINIO/m/<código-aleatorio>/archivo` (puerto 8097) y lo borra en cuanto se publica. Pon delante un proxy con https (Pangolin, Cloudflare Tunnel, Caddy…) **sin inicio de sesión**, porque quien entra es Instagram.

## Instalar o actualizar

En la máquina con Docker:

```
curl -fsSL https://raw.githubusercontent.com/iaonlineapps/instabot/main/update.sh | bash
```

La primera vez te pide el token de @BotFather. Luego, en Telegram: `/start` y `/token <llave de Instagram>`.

Ajustes (`.env`): `TELEGRAM_TOKEN`, `PUBLIC_URL` (tu dirección https), opcionales `TELEGRAM_OWNER_ID`, `INSTAGRAM_TOKEN`, `GRAPH_VERSION` (por defecto `v23.0`), `TELEGRAM_API_URL` (servidor propio de la API de bots, para vídeos de más de 20 MB).

## Comandos

`/estado` · `/token` · `/auto` · `/cancelar` · `/idioma` · `/novedades` · `/ayuda`

## Límites

- Telegram solo deja a los bots bajar archivos de hasta 20 MB (mándalo como vídeo normal, no como archivo, y Telegram lo comprime).
- Instagram: unos 100 posts al día por API, texto hasta 2.200 letras y 30 hashtags, carrusel hasta 10.

## Licencia

[PolyForm Noncommercial 1.0.0](LICENSE.md)
