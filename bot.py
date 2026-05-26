import logging
import os
import io
import asyncio
import aiohttp
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN')
# Free key from https://ocr.space/ocrapi (25,000 reqs/month).
# Fallback to the public 'helloworld' demo key if not set (very rate-limited).
OCR_API_KEY = os.environ.get('OCR_API_KEY', 'helloworld')
OCR_ENDPOINT = "https://api.ocr.space/parse/image"

# Limits
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB (OCR.space free-tier limit)

# Modes
MODE_PICK_LANG = "pick_lang"
MODE_WAIT_FILE = "wait_file"

# Supported OCR languages (OCR.space engine 1)
LANGS = [
    ("English", "eng"),
    ("Spanish", "spa"),
    ("French", "fre"),
    ("German", "ger"),
    ("Italian", "ita"),
    ("Portuguese", "por"),
    ("Dutch", "dut"),
    ("Russian", "rus"),
    ("Arabic", "ara"),
    ("Chinese (Simplified)", "chs"),
    ("Japanese", "jpn"),
    ("Korean", "kor"),
]


# ---------- Helpers ----------

def main_menu_markup() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🔍 Extract Text", callback_data="menu_extract")],
        [InlineKeyboardButton("🌐 Change Language", callback_data="menu_lang")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="menu_help")],
    ]
    return InlineKeyboardMarkup(keyboard)


def lang_markup() -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(LANGS), 2):
        row = []
        for name, code in LANGS[i:i+2]:
            row.append(InlineKeyboardButton(name, callback_data=f"lang_{code}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")])
    return InlineKeyboardMarkup(rows)


def reset_user_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop('mode', None)
    # Keep 'language' across sessions


def get_user_lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get('language', 'eng')


def get_lang_name(code: str) -> str:
    for name, c in LANGS:
        if c == code:
            return name
    return code


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ---------- Commands ----------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"User {user.id} started the bot")
    reset_user_state(context)

    lang_name = get_lang_name(get_user_lang(context))
    welcome = (
        "👋 *Welcome to OCR Text Extractor Bot!*\n\n"
        "I extract text from:\n"
        "• 🖼 Images (JPG, PNG, BMP, GIF, TIFF, WEBP)\n"
        "• 📄 PDF files (up to 3 pages)\n\n"
        f"🌐 *Current language:* {lang_name}\n"
        f"📏 *Max file size:* 5 MB\n\n"
        "Tap below to begin:"
    )
    await update.message.reply_text(welcome, reply_markup=main_menu_markup(), parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ *How to use*\n\n"
        "1. (Optional) Tap 🌐 *Change Language*\n"
        "2. Tap 🔍 *Extract Text*\n"
        "3. Send me an image or PDF\n"
        "4. Receive the extracted text\n\n"
        "💡 *Tips:*\n"
        "• Clear, well-lit images give best results\n"
        "• PDFs are limited to 3 pages on the free tier\n\n"
        "Use /cancel anytime to reset."
    )
    if update.message:
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=main_menu_markup())
    else:
        await update.callback_query.edit_message_text(
            text, parse_mode='Markdown', reply_markup=main_menu_markup()
        )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_user_state(context)
    await update.message.reply_text(
        "❌ Cancelled. Use /start to begin again.",
        reply_markup=main_menu_markup(),
    )


# ---------- Menu callbacks ----------

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_home":
        reset_user_state(context)
        lang_name = get_lang_name(get_user_lang(context))
        await query.edit_message_text(
            f"🏠 *Main Menu*\n🌐 Language: *{lang_name}*\n\nChoose an option below:",
            reply_markup=main_menu_markup(),
            parse_mode='Markdown',
        )

    elif data == "menu_help":
        await help_command(update, context)

    elif data == "menu_lang":
        context.user_data['mode'] = MODE_PICK_LANG
        await query.edit_message_text(
            "🌐 *Select OCR Language*\n\nChoose the language of the text in your file:",
            reply_markup=lang_markup(),
            parse_mode='Markdown',
        )

    elif data.startswith("lang_"):
        code = data.split("_", 1)[1]
        context.user_data['language'] = code
        name = get_lang_name(code)
        await query.edit_message_text(
            f"✅ Language set to *{name}*.",
            reply_markup=main_menu_markup(),
            parse_mode='Markdown',
        )

    elif data == "menu_extract":
        context.user_data['mode'] = MODE_WAIT_FILE
        lang_name = get_lang_name(get_user_lang(context))
        await query.edit_message_text(
            f"🔍 *Extract Mode*\n\n"
            f"🌐 Language: *{lang_name}*\n\n"
            "Send me an image or PDF file to extract text from.\n"
            "_Max 5 MB._",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")]]
            ),
        )


# ---------- File handlers ----------

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_incoming(update, context, update.message.document)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        return
    largest = update.message.photo[-1]
    fake_doc = type("Obj", (), {
        "file_id": largest.file_id,
        "file_name": f"photo_{largest.file_unique_id}.jpg",
        "file_size": largest.file_size,
        "mime_type": "image/jpeg",
    })()
    await handle_incoming(update, context, fake_doc)


async def handle_incoming(update, context, doc):
    mode = context.user_data.get('mode')
    if not doc:
        return

    if mode != MODE_WAIT_FILE:
        await update.message.reply_text(
            "Please tap 🔍 *Extract Text* first.",
            reply_markup=main_menu_markup(),
            parse_mode='Markdown',
        )
        return

    fname = (doc.file_name or "file").lower()
    allowed = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".tif", ".webp", ".pdf")
    if not fname.endswith(allowed):
        await update.message.reply_text(
            "⚠️ Unsupported file type. Send an image (JPG, PNG, BMP, GIF, TIFF, WEBP) or PDF."
        )
        return

    if doc.file_size and doc.file_size > MAX_FILE_SIZE:
        await update.message.reply_text(
            f"⚠️ File too large ({human_size(doc.file_size)}). Max is 5 MB."
        )
        return

    chat_id = update.effective_chat.id
    lang = get_user_lang(context)

    status = await update.message.reply_text(
        f"⏳ Extracting text ({get_lang_name(lang)})… please wait."
    )

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        buf = io.BytesIO()
        await tg_file.download_to_memory(out=buf)
        file_bytes = buf.getvalue()

        is_pdf = fname.endswith(".pdf")
        text = await ocr_extract(file_bytes, doc.file_name or "file", lang, is_pdf)

        await status.delete()

        if not text.strip():
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ No readable text found in this file.",
                reply_markup=main_menu_markup(),
            )
            return

        # If long → send as .txt file. Else inline.
        if len(text) > 3500:
            buf = io.BytesIO(text.encode("utf-8"))
            base = os.path.splitext(doc.file_name or "extracted")[0]
            await context.bot.send_document(
                chat_id=chat_id,
                document=InputFile(buf, filename=f"{base}_text.txt"),
                caption=f"✅ Extracted {len(text)} characters.",
                reply_markup=main_menu_markup(),
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ *Extracted text:*\n\n```\n{text}\n```",
                parse_mode='Markdown',
                reply_markup=main_menu_markup(),
            )

    except Exception as e:
        logger.error(f"OCR failed: {e}")
        try:
            await status.delete()
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ OCR failed: {e}",
            reply_markup=main_menu_markup(),
        )
    finally:
        reset_user_state(context)


# ---------- OCR API call ----------

async def ocr_extract(file_bytes: bytes, filename: str, language: str, is_pdf: bool) -> str:
    """Send the file to OCR.space and return extracted text."""
    timeout = aiohttp.ClientTimeout(total=90)
    data = aiohttp.FormData()
    data.add_field("file", file_bytes, filename=filename,
                   content_type="application/pdf" if is_pdf else "image/jpeg")
    data.add_field("language", language)
    data.add_field("isOverlayRequired", "false")
    data.add_field("detectOrientation", "true")
    data.add_field("scale", "true")
    data.add_field("OCREngine", "2")  # Better for Latin scripts
    if is_pdf:
        data.add_field("filetype", "PDF")

    headers = {"apikey": OCR_API_KEY}

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(OCR_ENDPOINT, data=data, headers=headers) as resp:
            if resp.status != 200:
                txt = await resp.text()
                raise RuntimeError(f"OCR.space HTTP {resp.status}: {txt[:200]}")
            result = await resp.json()

    if result.get("IsErroredOnProcessing"):
        msg = result.get("ErrorMessage") or result.get("ErrorDetails") or "Unknown error"
        if isinstance(msg, list):
            msg = "; ".join(str(m) for m in msg)
        raise RuntimeError(str(msg))

    parsed = result.get("ParsedResults") or []
    pages = [p.get("ParsedText", "") for p in parsed]
    return "\n\n".join(pages).strip()


# ---------- Dummy web server (keeps Render Web Service alive) ----------

async def health(request):
    return web.Response(text="Bot is running")


async def run_web():
    port = int(os.environ.get("PORT", 10000))
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health server listening on port {port}")


# ---------- Runner ----------

async def run_bot():
    if not BOT_TOKEN:
        logger.critical("FATAL: BOT_TOKEN is missing!")
        return

    try:
        application = Application.builder().token(BOT_TOKEN).build()

        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("cancel", cancel_command))
        application.add_handler(CallbackQueryHandler(menu_callback))
        application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

        await run_web()

        logger.info("Bot is now polling...")
        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)

        stop_event = asyncio.Event()
        await stop_event.wait()

    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
    finally:
        if 'application' in locals():
            await application.stop()
            await application.shutdown()


def main():
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.error(f"Main loop error: {e}")


if __name__ == '__main__':
    main()
