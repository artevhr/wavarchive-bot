import os, json, asyncio, logging, base64, re, time
from datetime import date
import urllib.request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, MessageHandler,
                           CallbackQueryHandler, ConversationHandler,
                           filters, ContextTypes)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN     = os.environ['BOT_TOKEN']
ADMIN_ID      = int(os.environ['ADMIN_ID'])
GITHUB_TOKEN  = os.environ['GITHUB_TOKEN']
GITHUB_OWNER  = os.environ.get('GITHUB_OWNER', 'artevhr')
GITHUB_REPO   = os.environ.get('GITHUB_REPO',  'wavarchive-music')
SITE_URL      = os.environ.get('SITE_URL', f'https://{GITHUB_OWNER}.github.io/wavarchive-site/')

TITLE, ARTIST, ALBUM, COVER, FILE = range(5)

pending: dict = {}


# ── /start ────────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text(
        "👋 Привет! Отправь свой трек на *WAVARCHIVE*.\n\n"
        "Я задам 5 вопросов по порядку. Начнём!\n\n"
        "1️⃣ Напиши *название трека*:",
        parse_mode="Markdown"
    )
    return TITLE


async def get_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data['title'] = update.message.text.strip()
    await update.message.reply_text(
        f"✅ *{ctx.user_data['title']}*\n\n2️⃣ Напиши *имя артиста*:",
        parse_mode="Markdown"
    )
    return ARTIST


async def get_artist(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data['artist'] = update.message.text.strip()
    await update.message.reply_text(
        f"✅ *{ctx.user_data['artist']}*\n\n3️⃣ Напиши *название альбома* (или «нет»):",
        parse_mode="Markdown"
    )
    return ALBUM


async def get_album(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    ctx.user_data['album'] = '' if val.lower() in ('нет', 'no', '-', 'none', '.') else val
    await update.message.reply_text(
        "4️⃣ Пришли *обложку альбома* (фото или файл).\n"
        "Если нет — напиши «нет»:",
        parse_mode="Markdown"
    )
    return COVER


async def get_cover(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.strip().lower() in ('нет', 'no', '-', 'none', '.'):
        ctx.user_data['cover_file_id'] = None
        ctx.user_data['cover_name']    = None
    elif update.message.photo:
        ctx.user_data['cover_file_id'] = update.message.photo[-1].file_id
        ctx.user_data['cover_name']    = 'cover.jpg'
    elif update.message.document:
        ctx.user_data['cover_file_id'] = update.message.document.file_id
        ctx.user_data['cover_name']    = update.message.document.file_name or 'cover.jpg'
    else:
        await update.message.reply_text("Пришли фото, файл-изображение или напиши «нет»:")
        return COVER
    await update.message.reply_text(
        "5️⃣ Последний шаг — пришли *файл трека* (MP3):",
        parse_mode="Markdown"
    )
    return FILE


async def get_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.audio:
        fid      = update.message.audio.file_id
        fname    = update.message.audio.file_name or f"{ctx.user_data.get('title','track')}.mp3"
        duration = update.message.audio.duration or 0
    elif update.message.document:
        fid      = update.message.document.file_id
        fname    = update.message.document.file_name or 'track.mp3'
        duration = 0
    else:
        await update.message.reply_text("Пришли аудио-файл (MP3):")
        return FILE

    ctx.user_data.update({
        'file_id':   fid,
        'file_name': fname,
        'duration':  duration,
        'from_id':   update.effective_user.id,
        'from_name': update.effective_user.full_name,
    })

    d = ctx.user_data
    caption = (
        f"🎵 *Новый трек на проверку*\n\n"
        f"👤 От: [{d['from_name']}](tg://user?id={d['from_id']}) `{d['from_id']}`\n"
        f"🎶 Название: *{d['title']}*\n"
        f"🎤 Артист: *{d['artist']}*\n"
        f"💿 Альбом: {d['album'] or '—'}\n"
        f"🕐 Длина: {duration}с\n"
        f"📁 Файл: `{fname}`"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_{d['from_id']}"),
        InlineKeyboardButton("❌ Отклонить",   callback_data=f"reject_{d['from_id']}")
    ]])

    if d.get('cover_file_id'):
        await ctx.bot.send_photo(ADMIN_ID, d['cover_file_id'], caption="⬆️ Обложка")

    admin_msg = await ctx.bot.send_document(
        ADMIN_ID, fid, caption=caption,
        parse_mode="Markdown", reply_markup=kb
    )

    pending[d['from_id']] = {**d, 'admin_msg_id': admin_msg.message_id}

    await update.message.reply_text(
        "✅ Трек отправлен на проверку!\n"
        "Как только админ рассмотрит заявку — ты получишь уведомление.\n\n"
        "Чтобы отправить ещё один трек — /start"
    )
    return ConversationHandler.END


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено. Напиши /start чтобы начать заново.")
    return ConversationHandler.END


# ── ADMIN CALLBACKS ───────────────────────────────────────────────────────────
async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_ID:
        await query.answer("Нет доступа", show_alert=True)
        return

    action, user_id_str = query.data.split('_', 1)
    user_id = int(user_id_str)
    sub = pending.get(user_id)

    if not sub:
        await query.edit_message_caption(
            (query.message.caption or '') + "\n\n⚠️ Данные устарели — перезапусти бота",
            parse_mode="Markdown"
        )
        return

    if action == 'approve':
        await query.edit_message_caption(
            (query.message.caption or '') + "\n\n⏳ Загружаю в GitHub...",
            parse_mode="Markdown"
        )
        try:
            await add_track_to_github(sub, ctx)
            await query.edit_message_caption(
                (query.message.caption or '') + "\n\n✅ *ПОДТВЕРЖДЕНО И ДОБАВЛЕНО*",
                parse_mode="Markdown"
            )
            await ctx.bot.send_message(
                user_id,
                f"🎉 Твой трек *{sub['title']}* одобрен и добавлен на WAVARCHIVE!\n\n"
                f"🎧 Слушай: {SITE_URL}",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"GitHub upload error: {e}")
            await query.edit_message_caption(
                (query.message.caption or '') + f"\n\n❌ Ошибка загрузки в GitHub: {e}",
                parse_mode="Markdown"
            )
        pending.pop(user_id, None)

    elif action == 'reject':
        ctx.bot_data[f'awaiting_reason_{user_id}'] = sub
        await ctx.bot.send_message(
            ADMIN_ID,
            f"Напиши причину отклонения трека *{sub['title']}*\n(или «—» без причины):",
            parse_mode="Markdown"
        )
        await query.edit_message_caption(
            (query.message.caption or '') + "\n\n⏳ Ожидаю причину отклонения...",
            parse_mode="Markdown"
        )


async def handle_admin_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    waiting = {k: v for k, v in ctx.bot_data.items() if k.startswith('awaiting_reason_')}
    if not waiting:
        return

    key, sub = next(iter(waiting.items()))
    user_id = sub['from_id']
    reason  = update.message.text.strip()

    msg = f"😔 Твой трек *{sub['title']}* был отклонён."
    if reason and reason not in ('—', '-', 'нет', 'no'):
        msg += f"\n\n📝 Причина: _{reason}_"
    msg += "\n\nЕсли хочешь попробовать снова — /start"

    await ctx.bot.send_message(user_id, msg, parse_mode="Markdown")
    await update.message.reply_text(
        f"✅ Трек *{sub['title']}* отклонён, артист уведомлён.",
        parse_mode="Markdown"
    )

    pending.pop(user_id, None)
    del ctx.bot_data[key]


# ── GITHUB API ────────────────────────────────────────────────────────────────
def gh_request(path: str, method: str = 'GET', body: dict = None):
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}"
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept':        'application/vnd.github.v3+json',
        'Content-Type':  'application/json',
        'User-Agent':    'WavArchiveBot/1.0'
    }
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


async def add_track_to_github(sub: dict, ctx: ContextTypes.DEFAULT_TYPE):
    # 1. Download MP3 from Telegram
    tg_file   = await ctx.bot.get_file(sub['file_id'])
    req       = urllib.request.Request(tg_file.file_path)
    with urllib.request.urlopen(req, timeout=60) as r:
        mp3_bytes = r.read()

    # 2. Build safe file path
    safe = lambda s: re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')
    artist_slug = safe(sub['artist'])
    title_slug  = safe(sub['title'])
    mp3_path    = f"tracks/{artist_slug}/{title_slug}.mp3"

    # 3. Upload MP3 — check if exists first
    try:
        existing = gh_request(mp3_path)
        sha_mp3  = existing.get('sha')
    except Exception:
        sha_mp3  = None

    upload_body = {
        'message': f'Add track: {sub["title"]} by {sub["artist"]}',
        'content': base64.b64encode(mp3_bytes).decode()
    }
    if sha_mp3:
        upload_body['sha'] = sha_mp3

    gh_request(mp3_path, 'PUT', upload_body)
    logger.info(f"MP3 uploaded: {mp3_path}")

    # 4. Get current tracks.json
    tracks_data = gh_request('tracks.json')
    current     = json.loads(base64.b64decode(tracks_data['content']).decode())
    sha_json    = tracks_data['sha']

    # 5. Build new track entry
    track_id  = f"{artist_slug}_{title_slug}_{int(time.time())}"
    new_track = {
        "id":          track_id,
        "title":       sub['title'],
        "artist":      sub['artist'],
        "album":       sub.get('album') or '',
        "genre":       "другое",
        "duration":    sub.get('duration', 0),
        "file":        mp3_path,
        "cover":       None,
        "albumCover":  None,
        "description": "",
        "tags":        [],
        "addedAt":     date.today().isoformat()
    }
    current.append(new_track)

    # 6. Push updated tracks.json
    updated = json.dumps(current, ensure_ascii=False, indent=2)
    gh_request('tracks.json', 'PUT', {
        'message': f'Add to catalog: {sub["title"]} by {sub["artist"]}',
        'content': base64.b64encode(updated.encode()).decode(),
        'sha':     sha_json
    })
    logger.info(f"tracks.json updated: {track_id}")


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            TITLE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, get_title)],
            ARTIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_artist)],
            ALBUM:  [MessageHandler(filters.TEXT & ~filters.COMMAND, get_album)],
            COVER:  [MessageHandler(
                (filters.PHOTO | filters.Document.IMAGE | filters.TEXT) & ~filters.COMMAND,
                get_cover
            )],
            FILE:   [MessageHandler(
                (filters.AUDIO | filters.Document.ALL) & ~filters.COMMAND,
                get_file
            )],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(handle_callback, pattern=r'^(approve|reject)_\d+$'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_message))

    logger.info("WAVARCHIVE Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
