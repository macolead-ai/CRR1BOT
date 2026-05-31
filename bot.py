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
OCR_API_KEY = os.environ.get('OCR_API_KEY', 'helloworld')
OCR_ENDPOINT = "https://api.ocr.space/parse/image"

# Limits
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

# Modes
MODE_PICK_LANG = "pick_lang"
MODE_PICK_UI_LANG = "pick_ui_lang"
MODE_WAIT_FILE = "wait_file"

# Supported OCR languages (Document languages)
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

# ---------- Localization Dictionary ----------

STRINGS = {
    "menu_extract": {"en": "🔍 Extract Text", "zh": "🔍 提取文字"},
    "menu_ocr_lang": {"en": "🌐 OCR Language", "zh": "🌐 识别语言"},
    "menu_ui_lang": {"en": "🗣 Bot Language", "zh": "🗣 界面语言"},
    "menu_help": {"en": "ℹ️ Help", "zh": "ℹ️ 帮助"},
    "menu_home": {"en": "🏠 Main Menu", "zh": "🏠 主菜单"},
    "welcome": {
        "en": "👋 *Welcome to OCR Text Extractor Bot!*\n\nI extract text from:\n• 🖼 Images (JPG, PNG, BMP, GIF, TIFF, WEBP)\n• 📄 PDF files (up to 3 pages)\n\n🌐 *OCR language:* {ocr_lang}\n🗣 *Bot language:* English\n📏 *Max file size:* 5 MB\n\nTap below to begin:",
        "zh": "👋 *欢迎使用 OCR 文字提取机器人！*\n\n我可以从以下文件中提取文字：\n• 🖼 图片 (JPG, PNG, BMP, GIF, TIFF, WEBP)\n• 📄 PDF 文件 (最多 3 页)\n\n🌐 *文档语言：* {ocr_lang}\n🗣 *界面语言：* 中文\n📏 *最大文件大小：* 5 MB\n\n请点击下方开始："
    },
    "help": {
        "en": "ℹ️ *How to use*\n\n1. (Optional) Tap 🌐 *OCR Language* to set document language\n2. Tap 🔍 *Extract Text*\n3. Send me an image or PDF\n4. Receive the extracted text\n\nUse /cancel anytime to reset.",
        "zh": "ℹ️ *使用说明*\n\n1. (可选) 点击 🌐 *识别语言* 设置文档语言\n2. 点击 🔍 *提取文字*\n3. 发送图片或 PDF 文件\n4. 接收提取的文字\n\n随时使用 /cancel 重置。"
    },
    "cancel": {
        "en": "❌ Cancelled. Use /start to begin again.",
        "zh": "❌ 已取消。请发送 /start 重新开始。"
    },
    "choose_ui_lang": {
        "en": "🗣 *Select Bot Language*\n\nChoose your preferred interface language:",
        "zh": "🗣 *选择界面语言*\n\n请选择您首选的机器人界面语言："
    },
    "choose_ocr_lang": {
        "en": "🌐 *Select OCR Language*\n\nChoose the language of the text in your file:",
        "zh": "🌐 *选择文档语言*\n\n请选择您文件中包含的文字语言："
    },
    "ocr_lang_set": {
        "en": "✅ OCR Language set to *{lang}*.",
        "zh": "✅ 文档语言已设置为 *{lang}*。"
    },
    "ui_lang_set": {
        "en": "✅ Bot language set to English.",
        "zh": "✅ 界面语言已切换为中文。"
    },
    "extract_mode": {
        "en": "🔍 *Extract Mode*\n\n🌐 OCR Language: *{lang}*\n\nSend me an image or PDF file to extract text from.\n_Max 5 MB._",
        "zh": "🔍 *提取模式*\n\n🌐 文档语言: *{lang}*\n\n请发送图片或 PDF 文件以提取文字。\n_最大支持 5 MB。_"
    },
    "tap_extract_first": {
        "en": "Please tap 🔍 *Extract Text* first.",
        "zh": "请先点击 🔍 *提取文字*。"
    },
    "unsupported_file": {
        "en": "⚠️ Unsupported file type. Send an image or PDF.",
        "zh": "⚠️ 不支持的文件类型。请发送图片或 PDF。"
    },
    "file_too_large": {
        "en": "⚠️ File too large ({size}). Max is 5 MB.",
        "zh": "⚠️ 文件过大 ({size})。最大支持 5 MB。"
    },
    "extracting": {
        "en": "⏳ Extracting text ({lang})… please wait.",
        "zh": "⏳ 正在提取文字 ({lang})… 请稍候。"
    },
    "no_text": {
        "en": "⚠️ No readable text found in this file.",
        "zh": "⚠️ 此文件中未找到可读文字。"
    },
    "extracted_chars": {
        "en": "✅ Extracted {count} characters.",
        "zh": "✅ 成功提取 {count} 个字符。"
    },
    "extracted_text": {
        "en": "✅ *Extracted text:*\n\n```\n{text}\n
```",
        "zh": "✅ *提取的文字：*\n\n```\n{text}\n```"
    },
    "ocr_failed": {
        "en": "❌ OCR failed: {error}",
        "zh": "❌ 识别失败：{error}"
    }
}

def _t(key: str, lang: str, **kwargs) -> str:
    """Helper function to fetch translated strings."""
    text = STRINGS.get(key, {}).get(lang, STRINGS.get(key, {}).get("en", key))
    return text.format(**kwargs) if kwargs else text


# ---------- Helpers ----------

def get_ui_lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get('ui_lang', 'en')

def main_menu_markup(ui_lang: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(_t("menu_extract", ui_lang), callback_data="menu_extract")],
        [
            InlineKeyboardButton(_t("menu_ocr_lang", ui_lang), callback_data="menu_lang"),
            InlineKeyboardButton(_t("menu_ui_lang", ui_lang), callback_data="menu_ui_lang")
        ],
        [InlineKeyboardButton(_t("menu_help", ui_lang), callback_data="menu_help")],
    ]
    return InlineKeyboardMarkup(keyboard)


def lang_markup(ui_lang: str) -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(LANGS), 2):
        row = []
        for name, code in LANGS[i:i+2]:
            row.append(InlineKeyboardButton(name, callback_data=f"lang_{code}"))
        rows.append(row)
    rows.append([InlineKeyboardButton(_t("menu_home", ui_lang), callback_data="menu_home")])
    return InlineKeyboardMarkup(rows)


def ui_lang_markup(ui_lang: str) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("🇬🇧 English", callback_data="uilang_en"),
            InlineKeyboardButton("🇨🇳 中文", callback_data="uilang_zh")
        ],
        [InlineKeyboardButton(_t("menu_home", ui_lang), callback_data="menu_home")]
    ]
    return InlineKeyboardMarkup(keyboard)


def reset_user_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop('mode', None)


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
    
    ui_lang = get_ui_lang(context)
    lang_name = get_lang_name(get_user_lang(context))
    
    welcome = _t("welcome", ui_lang, ocr_lang=lang_name)
    await update.message.reply_text(welcome, reply_markup=main_menu_markup(ui_lang), parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ui_lang = get_ui_lang(context)
    text = _t("help", ui_lang)
    
    if update.message:
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=main_menu_markup(ui_lang))
    else:
        await update.callback_query.edit_message_text(
            text, parse_mode='Markdown', reply_markup=main_menu_markup(ui_lang)
        )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_user_state(context)
    ui_lang = get_ui_lang(context)
    await update.message.reply_text(
        _t("cancel", ui_lang),
        reply_markup=main_menu_markup(ui_lang),
    )


# ---------- Menu callbacks ----------

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    ui_lang = get_ui_lang(context)

    if data == "menu_home":
        reset_user_state(context)
        await query.edit_message_text(
            f"🏠 {_t('menu_home', ui_lang)}",
            reply_markup=main_menu_markup(ui_lang),
            parse_mode='Markdown',
        )

    elif data == "menu_help":
        await help_command(update, context)

    # --- BOT INTERFACE LANGUAGE MENU ---
    elif data == "menu_ui_lang":
        context.user_data['mode'] = MODE_PICK_UI_LANG
        await query.edit_message_text(
            _t("choose_ui_lang", ui_lang),
            reply_markup=ui_lang_markup(ui_lang),
            parse_mode='Markdown',
        )

    elif data.startswith("uilang_"):
        code = data.split("_", 1)[1]
        context.user_data['ui_lang'] = code
        ui_lang = code  # Update local var immediately
        await query.edit_message_text(
            _t("ui_lang_set", ui_lang),
            reply_markup=main_menu_markup(ui_lang),
            parse_mode='Markdown',
        )

    # --- DOCUMENT OCR LANGUAGE MENU ---
    elif data == "menu_lang":
        context.user_data['mode'] = MODE_PICK_LANG
        await query.edit_message_text(
            _t("choose_ocr_lang", ui_lang),
            reply_markup=lang_markup(ui_lang),
            parse_mode='Markdown',
        )

    elif data.startswith("lang_"):
        code = data.split("_", 1)[1]
        context.user_data['language'] = code
        name = get_lang_name(code)
        await query.edit_message_text(
            _t("ocr_lang_set", ui_lang, lang=name),
            reply_markup=main_menu_markup(ui_lang),
            parse_mode='Markdown',
        )

    # --- EXTRACT MODE ---
    elif data == "menu_extract":
        context.user_data['mode'] = MODE_WAIT_FILE
        lang_name = get_lang_name(get_user_lang(context))
        await query.edit_message_text(
            _t("extract_mode", ui_lang, lang=lang_name),
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(_t("menu_home", ui_lang), callback_data="menu_home")]]
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
    ui_lang = get_ui_lang(context)
    
    if not doc:
        return

    if mode != MODE_WAIT_FILE:
        await update.message.reply_text(
            _t("tap_extract_first", ui_lang),
            reply_markup=main_menu_markup(ui_lang),
            parse_mode='Markdown',
        )
        return

    fname = (doc.file_name or "file").lower()
    allowed = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".tif", ".webp", ".pdf")
    if not fname.endswith(allowed):
        await update.message.reply_text(_t("unsupported_file", ui_lang))
        return

    if doc.file_size and doc.file_size > MAX_FILE_SIZE:
        await update.message.reply_text(_t("file_too_large", ui_lang, size=human_size(doc.file_size)))
        return

    chat_id = update.effective_chat.id
    ocr_lang_code = get_user_lang(context)
    lang_name = get_lang_name(ocr_lang_code)

    status = await update.message.reply_text(_t("extracting", ui_lang, lang=lang_name))

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        buf = io.BytesIO()
        await tg_file.download_to_memory(out=buf)
        file_bytes = buf.getvalue()

        is_pdf = fname.endswith(".pdf")
        text = await ocr_extract(file_bytes, doc.file_name or "file", ocr_lang_code, is_pdf)

        await status.delete()

        if not text.strip():
            await context.bot.send_message(
                chat_id=chat_id,
                text=_t("no_text", ui_lang),
                reply_markup=main_menu_markup(ui_lang),
            )
            return

        if len(text) > 3500:
            buf = io.BytesIO(text.encode("utf-8"))
            base = os.path.splitext(doc.file_name or "extracted")[0]
            await context.bot.send_document(
                chat_id=chat_id,
                document=InputFile(buf, filename=f"{base}_text.txt"),
                caption=_t("extracted_chars", ui_lang, count=len(text)),
                reply_markup=main_menu_markup(ui_lang),
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=_t("extracted_text", ui_lang, text=text),
                parse_mode='Markdown',
                reply_markup=main_menu_markup(ui_lang),
            )

    except Exception as e:
        logger.error(f"OCR failed: {e}")
        try:
            await status.delete()
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=chat_id,
            text=_t("ocr_failed", ui_lang, error=e),
            reply_markup=main_menu_markup(ui_lang),
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
    
    # FIX: OCR Engine 2 handles Latin scripts. Engine 1 is required for Asian/Arabic/Russian.
    engine = "2"
    if language in ["chs", "jpn", "kor", "ara", "rus"]:
        engine = "1"
    data.add_field("OCREngine", engine)
    
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
