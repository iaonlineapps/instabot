"""InstaBot: publica en Instagram lo que le mandas por Telegram.

Fotos -> post, varias fotos/vídeos juntos -> carrusel, vídeo -> Reel.
Usa la API oficial de Instagram (Instagram API with Instagram Login).
"""

import asyncio
import json
import logging
import os
import secrets
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from aiohttp import web
from PIL import Image, ImageFilter, ImageOps
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

VERSION = "1.0.0"

NOVEDADES = {
    "es": [
        "Primera versión.",
        "Mándame una foto y la publico como post.",
        "Varias fotos o vídeos a la vez: carrusel (hasta 10).",
        "Un vídeo: Reel (también sale en tu perfil).",
        "Antes de publicar te enseño un aviso con ✅ Publicar, ✏️ Cambiar texto y ❌ Cancelar.",
        "/estado te dice tu cuenta, los días que le quedan a la llave y los posts de hoy.",
        "La llave de Instagram se renueva sola.",
    ],
    "en": [
        "First version.",
        "Send me a photo and I post it.",
        "Several photos or videos at once: carousel (up to 10).",
        "A video: Reel (also shown on your profile).",
        "Before posting I show a preview with ✅ Post, ✏️ Change text and ❌ Cancel.",
        "/estado shows your account, days left on the key and today's posts.",
        "The Instagram key renews itself.",
    ],
}

log = logging.getLogger("instabot")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)

DATA = Path(os.environ.get("DATA_DIR", "/data"))
MEDIA = DATA / "media"
CONFIG_FILE = DATA / "config.json"
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
ENV_OWNER = os.environ.get("TELEGRAM_OWNER_ID", "").strip()
PUBLIC_URL = os.environ.get("PUBLIC_URL", "https://insta.familiapm.site").strip().rstrip("/")
PORT = int(os.environ.get("PORT", "8097"))
GRAPH_BASE = os.environ.get("GRAPH_BASE", "https://graph.instagram.com").strip().rstrip("/")
GRAPH = GRAPH_BASE + "/" + os.environ.get("GRAPH_VERSION", "v23.0").strip()
# Servidor propio de la API de bots (opcional, para vídeos de más de 20 MB)
TG_API_URL = os.environ.get("TELEGRAM_API_URL", "").strip().rstrip("/")
TG_MAX_DOWNLOAD = (2000 if TG_API_URL else 20) * 1024 * 1024
CAPTION_MAX = 2200
CAROUSEL_MAX = 10
DAY = 86400


# ----------------------------------------------------------------- textos

T = {
    "es": {
        "start_claimed": "👋 ¡Hola! Ya soy tu bot. Solo te haré caso a ti.\n\n",
        "help": (
            "📸 <b>InstaBot {v}</b>\n\n"
            "• Mándame <b>una foto</b> con el texto y la publico como post.\n"
            "• Mándame <b>varias fotos o vídeos juntos</b> (hasta 10) y hago un carrusel.\n"
            "• Mándame <b>un vídeo</b> y lo publico como Reel.\n\n"
            "El texto que pongas en la foto (el pie) será el texto del post. "
            "Antes de publicar te pregunto.\n\n"
            "<b>Comandos</b>\n"
            "/estado · cuenta, llave y posts de hoy\n"
            "/token · poner la llave de Instagram\n"
            "/auto · publicar sin preguntar (sí/no)\n"
            "/cancelar · borrar lo que tengas a medias\n"
            "/idioma · español / English\n"
            "/novedades · qué hay de nuevo"
        ),
        "need_token": (
            "🔑 Falta la llave de Instagram.\n\n"
            "Mándame <code>/token</code> seguido de la llave que copiaste en Meta, así:\n"
            "<code>/token IGAA...</code>"
        ),
        "token_bad": "❌ Esa llave no funciona: {e}",
        "token_ok": "✅ Llave guardada. Cuenta: <b>@{u}</b>. Ya puedes mandarme fotos y vídeos.",
        "token_deleted": "(He borrado tu mensaje con la llave para que no se quede en el chat.)",
        "too_big": "⚠️ Ese archivo pesa {mb} MB. Telegram solo deja a los bots bajar hasta 20 MB. Mándalo más pequeño (como vídeo normal, no como archivo, Telegram lo comprime).",
        "not_media": "Mándame fotos o vídeos. /ayuda para ver cómo.",
        "too_many": "⚠️ Un carrusel admite como mucho 10. Me quedo con los 10 primeros.",
        "downloading": "⏳ Recibiendo…",
        "preview": "📝 <b>{kind}</b> con {n} {what}\n\n<b>Texto:</b>\n{cap}\n\n¿Lo publico en @{u}?",
        "kind_photo": "Post",
        "kind_reel": "Reel",
        "kind_carousel": "Carrusel",
        "what_1": "archivo",
        "what_n": "archivos",
        "no_caption": "<i>(sin texto)</i>",
        "btn_post": "✅ Publicar",
        "btn_text": "✏️ Cambiar texto",
        "btn_cancel": "❌ Cancelar",
        "ask_text": "✏️ Escríbeme el texto nuevo (hasta 2.200 letras). Para dejarlo sin texto, manda un guion: -",
        "text_long": "⚠️ El texto tiene {n} letras y Instagram deja 2.200. Acórtalo y mándamelo otra vez.",
        "tags_many": "⚠️ Instagram deja como mucho 30 hashtags y hay {n}. Quita algunos y mándamelo otra vez.",
        "cancelled": "❌ Cancelado. No se ha publicado nada.",
        "gone": "Eso ya no está (se publicó, se canceló o pasó mucho tiempo).",
        "publishing": "🚀 Subiendo a Instagram…",
        "processing": "⏳ Instagram está preparando el vídeo… ({s} s)",
        "published": "✅ ¡Publicado en @{u}!\n{link}",
        "failed": "❌ No se ha podido publicar.\n\n<b>Instagram dice:</b> {e}\n\nNo se ha publicado nada. Puedes darle otra vez a ✅ Publicar.",
        "url_fail": "❌ Instagram no llega a los archivos en {url}. Revisa en Pangolin que el recurso existe y que tiene el SSO quitado.",
        "status": (
            "📊 <b>Estado</b> (InstaBot {v})\n\n"
            "Cuenta: <b>@{u}</b>\n"
            "Llave: le quedan <b>{d} días</b> (se renueva sola)\n"
            "Posts de hoy por el bot: <b>{q}</b> de {qmax}\n"
            "Dirección pública: {url} {ok}\n"
            "Publicar sin preguntar: {auto}"
        ),
        "status_notoken": "📊 InstaBot {v}\n\nAún no tengo la llave de Instagram.",
        "yes": "sí",
        "no": "no",
        "auto_on": "⚡ Ahora publico directamente, sin preguntar. /auto para volver a preguntar.",
        "auto_off": "🛑 Ahora te pregunto antes de publicar.",
        "nothing": "No tenías nada a medias.",
        "lang_pick": "Elige idioma / Choose language:",
        "lang_set": "✅ Idioma: español",
        "news": "✨ <b>Novedades de InstaBot {v}</b>\n\n{items}",
        "token_warn": "⚠️ La llave de Instagram caduca en {d} días y no he podido renovarla ({e}). Genera una nueva en Meta y mándamela con /token.",
        "token_expired": "⚠️ La llave de Instagram ha caducado o no vale. Genera una nueva en Meta y mándamela con /token.",
    },
    "en": {
        "start_claimed": "👋 Hi! I'm your bot now. I'll only listen to you.\n\n",
        "help": (
            "📸 <b>InstaBot {v}</b>\n\n"
            "• Send me <b>a photo</b> with text and I post it.\n"
            "• Send me <b>several photos or videos together</b> (up to 10) and I make a carousel.\n"
            "• Send me <b>a video</b> and I post it as a Reel.\n\n"
            "The caption you write becomes the post text. I ask before posting.\n\n"
            "<b>Commands</b>\n"
            "/estado · account, key and today's posts\n"
            "/token · set the Instagram key\n"
            "/auto · post without asking (on/off)\n"
            "/cancelar · drop what's pending\n"
            "/idioma · español / English\n"
            "/novedades · what's new"
        ),
        "need_token": (
            "🔑 The Instagram key is missing.\n\n"
            "Send me <code>/token</code> followed by the key you copied in Meta:\n"
            "<code>/token IGAA...</code>"
        ),
        "token_bad": "❌ That key doesn't work: {e}",
        "token_ok": "✅ Key saved. Account: <b>@{u}</b>. You can send me photos and videos now.",
        "token_deleted": "(I deleted your message with the key so it doesn't stay in the chat.)",
        "too_big": "⚠️ That file is {mb} MB. Telegram only lets bots download up to 20 MB. Send it smaller (as a normal video, not as a file; Telegram compresses it).",
        "not_media": "Send me photos or videos. /ayuda to see how.",
        "too_many": "⚠️ A carousel holds up to 10. I'll keep the first 10.",
        "downloading": "⏳ Receiving…",
        "preview": "📝 <b>{kind}</b> with {n} {what}\n\n<b>Text:</b>\n{cap}\n\nPost it on @{u}?",
        "kind_photo": "Post",
        "kind_reel": "Reel",
        "kind_carousel": "Carousel",
        "what_1": "file",
        "what_n": "files",
        "no_caption": "<i>(no text)</i>",
        "btn_post": "✅ Post",
        "btn_text": "✏️ Change text",
        "btn_cancel": "❌ Cancel",
        "ask_text": "✏️ Write the new text (up to 2,200 characters). To leave it empty, send a dash: -",
        "text_long": "⚠️ The text has {n} characters and Instagram allows 2,200. Shorten it and send it again.",
        "tags_many": "⚠️ Instagram allows up to 30 hashtags and there are {n}. Remove some and send it again.",
        "cancelled": "❌ Cancelled. Nothing was posted.",
        "gone": "That's gone (posted, cancelled or too old).",
        "publishing": "🚀 Uploading to Instagram…",
        "processing": "⏳ Instagram is processing the video… ({s} s)",
        "published": "✅ Posted on @{u}!\n{link}",
        "failed": "❌ Couldn't post.\n\n<b>Instagram says:</b> {e}\n\nNothing was posted. You can tap ✅ Post again.",
        "url_fail": "❌ Instagram can't reach the files at {url}. Check in Pangolin that the resource exists and has SSO turned off.",
        "status": (
            "📊 <b>Status</b> (InstaBot {v})\n\n"
            "Account: <b>@{u}</b>\n"
            "Key: <b>{d} days</b> left (renews itself)\n"
            "Posts today by the bot: <b>{q}</b> of {qmax}\n"
            "Public address: {url} {ok}\n"
            "Post without asking: {auto}"
        ),
        "status_notoken": "📊 InstaBot {v}\n\nI don't have the Instagram key yet.",
        "yes": "yes",
        "no": "no",
        "auto_on": "⚡ I now post straight away, without asking. /auto to ask again.",
        "auto_off": "🛑 I now ask before posting.",
        "nothing": "Nothing was pending.",
        "lang_pick": "Elige idioma / Choose language:",
        "lang_set": "✅ Language: English",
        "news": "✨ <b>What's new in InstaBot {v}</b>\n\n{items}",
        "token_warn": "⚠️ The Instagram key expires in {d} days and I couldn't renew it ({e}). Generate a new one in Meta and send it with /token.",
        "token_expired": "⚠️ The Instagram key has expired or is invalid. Generate a new one in Meta and send it with /token.",
    },
}


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ----------------------------------------------------------------- config


class Config:
    def __init__(self, path: Path):
        self.path = path
        self.d = {}
        if path.exists():
            try:
                self.d = json.loads(path.read_text())
            except Exception:
                log.exception("config.json dañado, empiezo de cero")

    def get(self, k, default=None):
        return self.d.get(k, default)

    def set(self, **kw):
        self.d.update(kw)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.d, indent=2))
        os.chmod(tmp, 0o600)
        tmp.replace(self.path)


cfg: Config = None  # se crea en main()


def owner_id():
    if ENV_OWNER:
        return int(ENV_OWNER)
    return cfg.get("owner_id")


def lang():
    return cfg.get("lang", "es")


def t(key, **kw):
    return T[lang()][key].format(v=VERSION, **kw)


# ----------------------------------------------------------------- Instagram


class IGError(Exception):
    pass


class Instagram:
    def __init__(self):
        self.http = httpx.AsyncClient(timeout=60)

    @staticmethod
    def _err(r: httpx.Response):
        try:
            e = r.json().get("error", {})
            msg = e.get("error_user_msg") or e.get("message") or r.text
            if e.get("error_user_title"):
                msg = f"{e['error_user_title']}: {msg}"
            return IGError(msg)
        except Exception:
            return IGError(f"HTTP {r.status_code}: {r.text[:300]}")

    async def get(self, path, token, **params):
        params["access_token"] = token
        r = await self.http.get(f"{GRAPH}/{path}", params=params)
        if r.status_code != 200:
            raise self._err(r)
        return r.json()

    async def post(self, path, token, **data):
        data["access_token"] = token
        r = await self.http.post(f"{GRAPH}/{path}", data=data)
        if r.status_code != 200:
            raise self._err(r)
        return r.json()

    async def me(self, token):
        j = await self.get("me", token, fields="user_id,username")
        if isinstance(j.get("data"), list) and j["data"]:
            j = j["data"][0]
        uid = j.get("user_id") or j.get("id")
        if not uid:
            raise IGError("no se pudo leer el id de la cuenta")
        return str(uid), j.get("username", "?")

    async def refresh(self, token):
        r = await self.http.get(
            f"{GRAPH_BASE}/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": token},
        )
        if r.status_code != 200:
            raise self._err(r)
        j = r.json()
        return j["access_token"], int(j.get("expires_in", 60 * DAY))

    async def container(self, ig, token, **data):
        j = await self.post(f"{ig}/media", token, **data)
        return j["id"]

    async def wait(self, cid, token, on_tick=None, timeout=900):
        start = time.time()
        while True:
            j = await self.get(cid, token, fields="status_code,status")
            code = j.get("status_code")
            if code in ("FINISHED", "PUBLISHED"):
                return
            if code in ("ERROR", "EXPIRED"):
                raise IGError(j.get("status") or code)
            waited = int(time.time() - start)
            if waited > timeout:
                raise IGError("Instagram tarda demasiado en preparar el archivo")
            if on_tick:
                await on_tick(waited)
            await asyncio.sleep(5)

    async def publish(self, ig, token, cid):
        # a veces el contenedor dice FINISHED pero aún no se puede publicar
        for i in range(6):
            try:
                j = await self.post(f"{ig}/media_publish", token, creation_id=cid)
                return j["id"]
            except IGError as e:
                if i == 5 or "not ready" not in str(e).lower():
                    raise
                await asyncio.sleep(5)

    async def permalink(self, mid, token):
        try:
            return (await self.get(mid, token, fields="permalink")).get("permalink", "")
        except IGError:
            return ""

    async def quota(self, ig, token):
        j = await self.get(f"{ig}/content_publishing_limit", token, fields="quota_usage,config")
        d = (j.get("data") or [{}])[0]
        return d.get("quota_usage", 0), (d.get("config") or {}).get("quota_total", 100)


ig_api: Instagram = None


# ----------------------------------------------------------------- borradores


@dataclass
class Item:
    kind: str  # "photo" | "video"
    path: Path


@dataclass
class Draft:
    id: str
    folder: Path
    items: list = field(default_factory=list)
    caption: str = ""
    created: float = field(default_factory=time.time)
    busy: bool = False

    @property
    def kind(self):
        if len(self.items) > 1:
            return "carousel"
        return "reel" if self.items[0].kind == "video" else "photo"


drafts: dict[str, Draft] = {}
waiting_text: dict = {"draft": None}  # borrador al que le falta el texto nuevo
groups: dict[str, dict] = {}  # álbumes de Telegram que van llegando


def new_folder():
    f = MEDIA / secrets.token_urlsafe(18)
    f.mkdir(parents=True, exist_ok=True)
    return f


def fit_ratio(r):
    return min(max(r, 0.8), 1.91)


def prepare_photo(src: Path, dst: Path, target=None):
    """JPEG, proporción entre 4:5 y 1.91:1 (rellena con la propia foto difuminada), máx. 1440 px."""
    im = Image.open(src)
    im = ImageOps.exif_transpose(im).convert("RGB")
    w, h = im.size
    r = w / h
    want = target if target else fit_ratio(r)
    if abs(r - want) > 0.01:
        if r < want:  # demasiado alta: ensanchar
            nw, nh = round(h * want), h
        else:  # demasiado ancha: alargar
            nw, nh = w, round(w / want)
        bg = ImageOps.fit(im, (nw, nh)).filter(ImageFilter.GaussianBlur(40))
        bg.paste(im, ((nw - w) // 2, (nh - h) // 2))
        im = bg
    if im.width > 1440:
        im = im.resize((1440, round(im.height * 1440 / im.width)), Image.LANCZOS)
    im.save(dst, "JPEG", quality=92, optimize=True)
    return im.width / im.height


async def download(msg, folder: Path, idx: int, bot):
    """Descarga la foto o el vídeo de un mensaje. Devuelve Item o lanza ValueError."""
    if msg.photo:
        f, kind, ext = msg.photo[-1], "photo", ".jpg"
    elif msg.video:
        f, kind, ext = msg.video, "video", ".mp4"
    elif msg.animation:
        f, kind, ext = msg.animation, "video", ".mp4"
    elif msg.document and (msg.document.mime_type or "").startswith("image/"):
        f, kind, ext = msg.document, "photo", ".img"
    elif msg.document and (msg.document.mime_type or "").startswith("video/"):
        f, kind, ext = msg.document, "video", ".mp4"
    else:
        raise ValueError("not_media")
    if (f.file_size or 0) > TG_MAX_DOWNLOAD:
        raise ValueError(f"too_big:{f.file_size / 1048576:.0f}")
    tf = await bot.get_file(f.file_id)
    raw = folder / f"raw{idx}{ext}"
    await tf.download_to_drive(raw)
    if kind == "photo":
        return Item("photo", raw)
    out = folder / f"{idx}.mp4"
    raw.rename(out)
    return Item("video", out)


def finalize_photos(d: Draft):
    target = None
    for i, it in enumerate(d.items):
        if it.kind != "photo":
            continue
        out = d.folder / f"{i}.jpg"
        r = prepare_photo(it.path, out, target if len(d.items) > 1 else None)
        if len(d.items) > 1 and target is None:
            target = r  # en un carrusel todas con la proporción de la primera
        if it.path != out:
            it.path.unlink(missing_ok=True)
        it.path = out


def url_of(p: Path):
    return f"{PUBLIC_URL}/m/{p.parent.name}/{p.name}"


def keyboard(did):
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t("btn_post"), callback_data=f"pub:{did}")],
            [
                InlineKeyboardButton(t("btn_text"), callback_data=f"txt:{did}"),
                InlineKeyboardButton(t("btn_cancel"), callback_data=f"del:{did}"),
            ],
        ]
    )


def preview_text(d: Draft):
    n = len(d.items)
    cap = esc(d.caption) if d.caption else t("no_caption")
    return t(
        "preview",
        kind=t("kind_" + d.kind),
        n=n,
        what=t("what_1" if n == 1 else "what_n"),
        cap=cap,
        u=esc(cfg.get("username", "?")),
    )


def check_caption(c: str):
    if len(c) > CAPTION_MAX:
        return t("text_long", n=len(c))
    tags = sum(1 for w in c.split() if w.startswith("#"))
    if tags > 30:
        return t("tags_many", n=tags)
    return None


def drop(d: Draft):
    drafts.pop(d.id, None)
    if waiting_text["draft"] == d.id:
        waiting_text["draft"] = None
    shutil.rmtree(d.folder, ignore_errors=True)


# ----------------------------------------------------------------- publicar


async def publish(d: Draft, bot, chat_id):
    token, ig = cfg.get("ig_token"), cfg.get("ig_user_id")
    status = await bot.send_message(chat_id, t("publishing"))
    last = {"s": -10}

    async def tick(s):
        if s - last["s"] >= 15:
            last["s"] = s
            try:
                await status.edit_text(t("processing", s=s))
            except Exception:
                pass

    cap = d.caption or ""
    try:
        if d.kind == "photo":
            cid = await ig_api.container(ig, token, image_url=url_of(d.items[0].path), caption=cap)
            await ig_api.wait(cid, token, tick)
        elif d.kind == "reel":
            cid = await ig_api.container(
                ig, token, media_type="REELS", video_url=url_of(d.items[0].path),
                caption=cap, share_to_feed="true",
            )
            await ig_api.wait(cid, token, tick)
        else:
            children = []
            for it in d.items:
                if it.kind == "photo":
                    c = await ig_api.container(ig, token, image_url=url_of(it.path), is_carousel_item="true")
                else:
                    c = await ig_api.container(
                        ig, token, media_type="VIDEO", video_url=url_of(it.path), is_carousel_item="true"
                    )
                children.append(c)
            for c in children:
                await ig_api.wait(c, token, tick)
            cid = await ig_api.container(ig, token, media_type="CAROUSEL", children=",".join(children), caption=cap)
            await ig_api.wait(cid, token, tick)
        mid = await ig_api.publish(ig, token, cid)
        link = await ig_api.permalink(mid, token)
    except IGError as e:
        log.warning("fallo al publicar: %s", e)
        s = str(e)
        if "media" in s.lower() and ("download" in s.lower() or "fetch" in s.lower() or "uri" in s.lower()):
            txt = t("url_fail", url=esc(PUBLIC_URL))
        else:
            txt = t("failed", e=esc(s))
        await status.edit_text(txt, parse_mode=ParseMode.HTML)
        if d.id in drafts:
            await bot.send_message(chat_id, preview_text(d), parse_mode=ParseMode.HTML, reply_markup=keyboard(d.id))
        return False
    await status.edit_text(t("published", u=esc(cfg.get("username", "?")), link=link), parse_mode=ParseMode.HTML)
    drop(d)
    return True


async def offer(d: Draft, bot, chat_id):
    drafts[d.id] = d
    if not cfg.get("ig_token"):
        await bot.send_message(chat_id, t("need_token"), parse_mode=ParseMode.HTML)
    if cfg.get("auto") and cfg.get("ig_token"):
        d.busy = True
        await publish(d, bot, chat_id)
        d.busy = False
    else:
        await bot.send_message(chat_id, preview_text(d), parse_mode=ParseMode.HTML, reply_markup=keyboard(d.id))


# ----------------------------------------------------------------- Telegram


def is_owner(update: Update):
    u = update.effective_user
    return u is not None and owner_id() is not None and u.id == owner_id()


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    prefix = ""
    if owner_id() is None and update.effective_chat.type == "private":
        cfg.set(owner_id=update.effective_user.id, last_version=VERSION)
        prefix = t("start_claimed")
        log.info("dueño del bot: %s", update.effective_user.id)
    if not is_owner(update):
        return
    await update.message.reply_text(prefix + t("help"), parse_mode=ParseMode.HTML)
    if not cfg.get("ig_token"):
        await update.message.reply_text(t("need_token"), parse_mode=ParseMode.HTML)


async def cmd_help(update: Update, ctx):
    if is_owner(update):
        await update.message.reply_text(t("help"), parse_mode=ParseMode.HTML)


async def cmd_token(update: Update, ctx):
    if not is_owner(update):
        return
    tok = " ".join(ctx.args).strip()
    try:
        await update.message.delete()
        deleted = True
    except Exception:
        deleted = False
    if not tok:
        await ctx.bot.send_message(update.effective_chat.id, t("need_token"), parse_mode=ParseMode.HTML)
        return
    try:
        uid, user = await ig_api.me(tok)
    except Exception as e:
        await ctx.bot.send_message(update.effective_chat.id, t("token_bad", e=esc(str(e))), parse_mode=ParseMode.HTML)
        return
    now = time.time()
    cfg.set(ig_token=tok, ig_user_id=uid, username=user, token_set_at=now, token_expires_at=now + 60 * DAY)
    msg = t("token_ok", u=esc(user))
    if deleted:
        msg += "\n\n" + t("token_deleted")
    await ctx.bot.send_message(update.effective_chat.id, msg, parse_mode=ParseMode.HTML)


async def url_ok():
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{PUBLIC_URL}/salud")
            return r.status_code == 200 and r.text.strip() == "ok"
    except Exception:
        return False


async def cmd_status(update: Update, ctx):
    if not is_owner(update):
        return
    if not cfg.get("ig_token"):
        await update.message.reply_text(t("status_notoken") + "\n\n" + t("need_token"), parse_mode=ParseMode.HTML)
        return
    try:
        q, qmax = await ig_api.quota(cfg.get("ig_user_id"), cfg.get("ig_token"))
    except Exception as e:
        q, qmax = "?", "?"
        log.warning("quota: %s", e)
    days = max(0, int((cfg.get("token_expires_at", 0) - time.time()) / DAY))
    ok = "✅" if await url_ok() else "❌"
    await update.message.reply_text(
        t(
            "status", u=esc(cfg.get("username", "?")), d=days, q=q, qmax=qmax,
            url=esc(PUBLIC_URL), ok=ok, auto=t("yes") if cfg.get("auto") else t("no"),
        ),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def cmd_auto(update: Update, ctx):
    if not is_owner(update):
        return
    on = not cfg.get("auto", False)
    cfg.set(auto=on)
    await update.message.reply_text(t("auto_on" if on else "auto_off"))


async def cmd_cancel(update: Update, ctx):
    if not is_owner(update):
        return
    pending = [d for d in drafts.values() if not d.busy]
    for d in pending:
        drop(d)
    await update.message.reply_text(t("cancelled") if pending else t("nothing"))


async def cmd_lang(update: Update, ctx):
    if not is_owner(update):
        return
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🇪🇸 Español", callback_data="lang:es"),
          InlineKeyboardButton("🇬🇧 English", callback_data="lang:en")]]
    )
    await update.message.reply_text(t("lang_pick"), reply_markup=kb)


def news_text():
    return t("news", items="\n".join("• " + esc(x) for x in NOVEDADES[lang()]))


async def cmd_news(update: Update, ctx):
    if is_owner(update):
        await update.message.reply_text(news_text(), parse_mode=ParseMode.HTML)


async def on_media(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return
    msg = update.effective_message
    chat_id = update.effective_chat.id
    if msg.media_group_id:
        g = groups.get(msg.media_group_id)
        if g is None:
            g = groups[msg.media_group_id] = {"msgs": [], "chat": chat_id}
        g["msgs"].append(msg)
        for job in ctx.job_queue.get_jobs_by_name(msg.media_group_id):
            job.schedule_removal()
        ctx.job_queue.run_once(finish_group, 2.5, data=msg.media_group_id, name=msg.media_group_id)
        return
    await build_draft([msg], chat_id, ctx.bot)


async def finish_group(ctx: ContextTypes.DEFAULT_TYPE):
    g = groups.pop(ctx.job.data, None)
    if g:
        msgs = sorted(g["msgs"], key=lambda m: m.message_id)
        await build_draft(msgs, g["chat"], ctx.bot)


async def build_draft(msgs, chat_id, bot):
    if len(msgs) > CAROUSEL_MAX:
        await bot.send_message(chat_id, t("too_many"))
        msgs = msgs[:CAROUSEL_MAX]
    note = await bot.send_message(chat_id, t("downloading"))
    d = Draft(id=uuid.uuid4().hex[:10], folder=new_folder())
    try:
        for i, m in enumerate(msgs):
            d.items.append(await download(m, d.folder, i, bot))
            if m.caption and not d.caption:
                d.caption = m.caption
        await asyncio.to_thread(finalize_photos, d)
    except ValueError as e:
        shutil.rmtree(d.folder, ignore_errors=True)
        s = str(e)
        if s.startswith("too_big:"):
            await note.edit_text(t("too_big", mb=s.split(":")[1]))
        else:
            await note.edit_text(t("not_media"))
        return
    except Exception as e:
        log.exception("error preparando")
        shutil.rmtree(d.folder, ignore_errors=True)
        await note.edit_text(t("failed", e=esc(str(e))), parse_mode=ParseMode.HTML)
        return
    try:
        await note.delete()
    except Exception:
        pass
    err = check_caption(d.caption)
    if err:
        await bot.send_message(chat_id, err)
    await offer(d, bot, chat_id)


async def on_text(update: Update, ctx):
    if not is_owner(update):
        return
    did = waiting_text["draft"]
    d = drafts.get(did) if did else None
    if not d:
        await update.message.reply_text(t("not_media"))
        return
    txt = update.message.text
    new = "" if txt.strip() == "-" else txt
    err = check_caption(new)
    if err:
        await update.message.reply_text(err)
        return
    d.caption = new
    waiting_text["draft"] = None
    await update.message.reply_text(preview_text(d), parse_mode=ParseMode.HTML, reply_markup=keyboard(d.id))


async def on_button(update: Update, ctx):
    q = update.callback_query
    if not is_owner(update):
        await q.answer()
        return
    await q.answer()
    action, _, arg = q.data.partition(":")
    if action == "lang":
        cfg.set(lang=arg)
        await q.edit_message_text(t("lang_set"))
        return
    d = drafts.get(arg)
    if not d:
        await q.edit_message_reply_markup(None)
        await q.message.reply_text(t("gone"))
        return
    if action == "del":
        drop(d)
        await q.edit_message_text(t("cancelled"))
    elif action == "txt":
        waiting_text["draft"] = d.id
        await q.message.reply_text(t("ask_text"))
    elif action == "pub":
        if d.busy:
            return
        if not cfg.get("ig_token"):
            await q.message.reply_text(t("need_token"), parse_mode=ParseMode.HTML)
            return
        err = check_caption(d.caption)
        if err:
            await q.message.reply_text(err)
            return
        d.busy = True
        await q.edit_message_reply_markup(None)
        try:
            await publish(d, ctx.bot, q.message.chat_id)
        finally:
            d.busy = False


# ----------------------------------------------------------------- tareas


async def job_token(ctx: ContextTypes.DEFAULT_TYPE):
    """Renueva la llave cada semana (dura 60 días)."""
    tok = cfg.get("ig_token")
    if not tok:
        return
    now = time.time()
    if now - cfg.get("token_set_at", 0) < 7 * DAY:
        return
    try:
        new, exp = await ig_api.refresh(tok)
        cfg.set(ig_token=new, token_set_at=now, token_expires_at=now + exp)
        log.info("llave renovada, caduca en %d días", exp // DAY)
    except Exception as e:
        log.warning("no se pudo renovar la llave: %s", e)
        left = int((cfg.get("token_expires_at", 0) - now) / DAY)
        oid = owner_id()
        if oid and left <= 10:
            key = "token_expired" if left <= 0 else "token_warn"
            await ctx.bot.send_message(oid, t(key, d=left, e=esc(str(e))))


async def job_clean(ctx):
    """Borra borradores y archivos de más de 2 días."""
    limit = time.time() - 2 * DAY
    for d in list(drafts.values()):
        if d.created < limit and not d.busy:
            drop(d)
    active = {d.folder.name for d in drafts.values()}
    for f in MEDIA.iterdir() if MEDIA.exists() else []:
        if f.name not in active and f.stat().st_mtime < limit:
            shutil.rmtree(f, ignore_errors=True)


# ----------------------------------------------------------------- web (archivos para Instagram)


async def serve_media(request: web.Request):
    folder, name = request.match_info["folder"], request.match_info["name"]
    if "/" in folder or "/" in name or folder.startswith(".") or name.startswith("."):
        raise web.HTTPNotFound()
    p = MEDIA / folder / name
    if not p.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(p, headers={"Cache-Control": "no-store"})


async def health(request):
    return web.Response(text="ok")


async def not_found(request):
    raise web.HTTPNotFound()


async def start_web():
    app = web.Application()
    app.router.add_get("/m/{folder}/{name}", serve_media)
    app.router.add_get("/salud", health)
    app.router.add_get("/", not_found)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    log.info("archivos en %s (puerto %d)", PUBLIC_URL, PORT)


async def post_init(app: Application):
    await start_web()
    from telegram import BotCommand

    await app.bot.set_my_commands(
        [
            BotCommand("estado", "Estado / status"),
            BotCommand("token", "Llave de Instagram / Instagram key"),
            BotCommand("auto", "Publicar sin preguntar / post without asking"),
            BotCommand("cancelar", "Cancelar / cancel"),
            BotCommand("idioma", "Idioma / language"),
            BotCommand("novedades", "Novedades / what's new"),
            BotCommand("ayuda", "Ayuda / help"),
        ]
    )
    oid = owner_id()
    if oid and cfg.get("last_version") != VERSION:
        try:
            await app.bot.send_message(oid, news_text(), parse_mode=ParseMode.HTML)
        except Exception:
            log.exception("no pude mandar las novedades")
        cfg.set(last_version=VERSION)
    app.job_queue.run_repeating(job_token, interval=6 * 3600, first=60)
    app.job_queue.run_repeating(job_clean, interval=3600, first=120)


def main():
    global cfg, ig_api
    if not TG_TOKEN:
        raise SystemExit("Falta TELEGRAM_TOKEN en el .env")
    MEDIA.mkdir(parents=True, exist_ok=True)
    cfg = Config(CONFIG_FILE)
    env_ig = os.environ.get("INSTAGRAM_TOKEN", "").strip()
    if env_ig and not cfg.get("ig_token"):
        cfg.set(ig_token=env_ig, token_set_at=time.time(), token_expires_at=time.time() + 60 * DAY)
    ig_api = Instagram()
    b = Application.builder().token(TG_TOKEN).post_init(post_init)
    if TG_API_URL:
        b = b.base_url(f"{TG_API_URL}/bot").base_file_url(f"{TG_API_URL}/file/bot")
    app = b.build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler(["ayuda", "help"], cmd_help))
    app.add_handler(CommandHandler("token", cmd_token))
    app.add_handler(CommandHandler(["estado", "status"], cmd_status))
    app.add_handler(CommandHandler("auto", cmd_auto))
    app.add_handler(CommandHandler(["cancelar", "cancel"], cmd_cancel))
    app.add_handler(CommandHandler(["idioma", "language"], cmd_lang))
    app.add_handler(CommandHandler(["novedades", "news"], cmd_news))
    app.add_handler(CallbackQueryHandler(on_button))
    media = filters.PHOTO | filters.VIDEO | filters.ANIMATION | filters.Document.IMAGE | filters.Document.VIDEO
    app.add_handler(MessageHandler(media, on_media))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)


if __name__ == "__main__":
    main()
