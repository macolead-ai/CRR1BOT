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

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN')
OCR_API_KEY = os.environ.get('OCR_API_KEY', 'helloworld')
OCR_ENDPOINT = "https://api.ocr.space/parse/image"

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

MODE_PICK_LANG = "pick_lang"
MODE_WAIT_FILE = "wait_file"

# OCR engine languages — (English name, Chinese name, code)
LANGS = [
    ("English", "英文", "eng"),
    ("Spanish", "西班牙文", "spa"),
    ("French", "法文", "fre"),
    ("German", "德文", "ger"),
    ("Italian", "意大利文", "ita"),
    ("Portuguese", "葡萄牙文", "por"),
    ("Dutch", "荷兰文", "dut"),
    ("Russian", "俄文", "rus"),
    ("Arabic", "阿拉伯文", "ara"),
    ("Chinese (Simplified)", "中文（简体）", "chs"),
    ("Japanese", "日文", "jpn"),
    ("Korean", "韩文", "kor"),
]

# UI / bot-conversation languages
UI_LANGS = [("English", "en"), ("中文", "zh")]
UI_LANG_NAME = {"en": "English", "zh": "中文"}

# ---------- i18n ----------
T = {
    "en": {
        "welcome": ("👋 *Welcome to OCR Text Extractor Bot!*\n\n"
                    "I extract text from:\n"
                    "• 🖼 Images (JPG, PNG, BMP, GIF, TIFF, WEBP)\n"
                    "• 📄 PDF files (up to 3 pages)\n\n"
                    "🌐 *OCR language:* {lang}\n"
                    "🗣 *Bot language:* {ui}\n"
                    "📏 *Max file size:* 5 MB\n\n"
                    "Tap below to begin:"),
        "help": ("ℹ️ *How to use*\n\n"
                 "1. (Optional) Tap 🌐 *OCR Language* to set the language to detect\n"
                 "2. Tap 🔍 *Extract Text*\n"
                 "3. Send me an image or PDF\n"
                 "4. Receive the extracted text\n\n"
                 "💡 *Tips:*\n"
                 "• Clear, well-lit images give best results\n"
                 "• PDFs are limited to 3 pages on the free tier\n\n"
                 "Use /cancel anytime to reset."),
        "cancelled": "❌ Cancelled. Use /start to begin again.",
        "btn_extract": "🔍 Extract Text",
        "btn_ocr_lang": "🌐 OCR Language",
        "btn_ui_lang": "🗣 Bot Language",
        "btn_help": "ℹ️ Help",
        "btn_home": "🏠 Main Menu",
        "home": ("🏠 *Main Menu*\n"
                 "🌐 OCR: *{lang}*\n"
                 "🗣 Bot: *{ui}*\n\n"
                 "Choose an option below:"),
        "pick_ocr": "🌐 *Select OCR Language*\n\nChoose the language of the text in your file:",
        "pick_ui": "🗣 *Select Bot Language*\n\nChoose how I should talk to you:",
        "lang_set": "✅ OCR language set to *{name}*.",
        "ui_set": "✅ Bot language set to *{name}*.",
        "extract_prompt": ("🔍 *Extract Mode*\n\n"
                           "🌐 OCR language: *{lang}*\n\n"
                           "Send me an image or PDF file to extract text from.\n"
                           "_Max 5 MB._"),
        "tap_extract_first": "Please tap 🔍 *Extract Text* first.",
        "unsupported": "⚠️ Unsupported file type. Send an image (JPG, PNG, BMP, GIF, TIFF, WEBP) or PDF.",
        "too_large": "⚠️ File too large ({size}). Max is 5 MB.",
        "extracting": "⏳ Extracting text ({lang})… please wait.",
        "no_text": "⚠️ No readable text found in this file.",
        "extracted_caption": "✅ Extracted {n} characters.",
        "extracted_inline": "✅ *Extracted text:*\n\n```\n{text}\n```",
        "ocr_failed": "❌ OCR failed: {err}",
    },
    "zh": {
        "welcome": ("👋 *欢迎使用OCR文字提取机器人！*\n\n"
                    "我可以从以下文件提取文字：\n"
                    "• 🖼 图片（JPG, PNG, BMP, GIF, TIFF, WEBP）\n"
                    "• 📄 PDF文件（最多3页）\n\n"
                    "🌐 *OCR识别语言：* {lang}\n"
                    "🗣 *机器人语言：* {ui}\n"
                    "📏 *最大文件大小：* 5 MB\n\n"
                    "点击下方按钮开始："),
        "help": ("ℹ️ *使用方法*\n\n"
                 "1.（可选）点击 🌐 *OCR语言* 设置要识别的文字语言\n"
                 "2. 点击 🔍 *提取文字*\n"
                 "3. 发送图片或PDF文件\n"
                 "4. 获取提取的文字\n\n"
                 "💡 *小贴士：*\n"
                 "• 清晰、光线充足的图片效果最佳\n"
                 "• 免费版PDF限制3页\n\n"
                 "随时使用 /cancel 重置。"),
        "cancelled": "❌ 已取消。使用 /start 重新开始。",
        "btn_extract": "🔍 提取文字",
        "btn_ocr_lang": "🌐 OCR语言",
        "btn_ui_lang": "🗣 机器人语言",
        "btn_help": "ℹ️ 帮助",
        "btn_home": "🏠 主菜单",
        "home": ("🏠 *主菜单*\n"
                 "🌐 OCR：*{lang}*\n"
                 "🗣 机器人：*{ui}*\n\n"
                 "请选择："),
        "pick_ocr": "🌐 *选择OCR识别语言*\n\n请选择文件中的文字语言：",
        "pick_ui": "🗣 *选择机器人语言*\n\n请选择我与您交流的语言：",
        "lang_set": "✅ OCR语言已设置为 *{name}*。",
        "ui_set": "✅ 机器人语言已设置为 *{name}*。",
        "extract_prompt": ("🔍 *提取模式*\n\n"
                           "🌐 OCR语言：*{lang}*\n\n"
                           "请发送图片或PDF文件以提取文字。\n"
                           "_最大5 MB。_"),
        "tap_extract_first": "请先点击 🔍 *提取文字*。",
        "unsupported": "⚠️ 不支持的文件类型。请发送图片（JPG, PNG, BMP, GIF, TIFF, WEBP）或PDF。",
        "too_large": "⚠️ 文件过大（{size}）。最大支持5 MB。",
        "extracting": "⏳ 正在提取文字（{lang}）…请稍候。",
        "no_text": "⚠️ 此文件中未找到可识别的文字。",
        "extracted_caption": "✅ 已提取 {n} 个字符。",
        "extracted_inline": "✅ *提取的文字：*\n\n```\n{text}\n```",
        "ocr_failed": "❌ OCR失败：{err}",
    },
}


# ---------- Helpers ----------

def get_ui_lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get('ui_lang', 'en')

def t(context: ContextTypes.DEFAULT_TYPE, key: str, **fmt) -> str:
    ui = get_ui_lang(context)
    s = T.get(ui, T["en"]).get(key) or T["en"].get(key, key)
    return s.format(**fmt) if fmt else s

def get_user_lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get('language', 'eng')

def get_lang_name(code: str, ui_lang: str = "en") -> str:
    for en_name, zh_name, c in LANGS:
        if c == code:
            return zh_name if ui_lang == "zh" else en_name
    return code

def reset_user_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop('mode', None)
    # Keep 'language' and 'ui_lang' across sessions

def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def main_menu_markup(context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(context, "btn_extract"), callback_data="menu_extract")],
        [InlineKeyboardButton(t(context, "btn_ocr_lang"), callback_data="menu_lang")],
        [InlineKeyboardButton(t(context, "btn_ui_lang"), callback_data="menu_ui")],
        [InlineKeyboardButton(t(context, "btn_help"), callback_data="menu_help")],
    ])

def lang_markup(context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    ui = get_ui_lang(context)
    rows = []
    for i in range(0, len(LANGS), 2):
        row = []
        for en_name, zh_name, code in LANGS[i:i+2]:
            label = zh_name if ui == "zh" else en_name
            row.append(InlineKeyboardButton(label, callback_data=f"lang_{code}"))
        rows.append(row)
    rows.append([InlineKeyboardButton(t(context, "btn_home"), callback_data="menu_home")])
    return InlineKeyboardMarkup(rows)

def ui_markup(context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(name, callback_data=f"ui_{code}")] for name, code in UI_LANGS]
    rows.append([InlineKeyboardButton(t(context, "btn_home"), callback_data="menu_home")])
    return InlineKeyboardMarkup(rows)


# ---------- Commands ----------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"User {user.id} started the bot")
    reset_user_state(context)
    ui = get_ui_lang(context)
    welcome = t(context, "welcome",
                lang=get_lang_name(get_user_lang(context), ui),
                ui=UI_LANG_NAME[ui])
    await update.message.reply_text(welcome, reply_markup=main_menu_markup(context), parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = t(context, "help")
    if update.message:
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=main_menu_markup(context))
    else:
        await update.callback_query.edit_message_text(
            text, parse_mode='Markdown', reply_markup=main_menu_markup(context)
        )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_user_state(context)
    await update.message.reply_text(
        t(context, "cancelled"),
        reply_markup=main_menu_markup(context),
    )


# ---------- Menu callbacks ----------

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_home":
        reset_user_state(context)
        ui = get_ui_lang(context)
        await query.edit_message_text(
            t(context, "home",
              lang=get_lang_name(get_user_lang(context), ui),
              ui=UI_LANG_NAME[ui]),
            reply_markup=main_menu_markup(context),
            parse_mode='Markdown',
        )

    elif data == "menu_help":
        await help_command(update, context)

    elif data == "menu_lang":
        context.user_data['mode'] = MODE_PICK_LANG
        await query.edit_message_text(
            t(context, "pick_ocr"),
            reply_markup=lang_markup(context),
            parse_mode='Markdown',
        )

    elif data == "menu_ui":
        await query.edit_message_text(
            t(context, "pick_ui"),
            reply_markup=ui_markup(context),
            parse_mode='Markdown',
        )

    elif data.startswith("lang_"):
        code = data.split("_", 1)[1]
        context.user_data['language'] = code
        await query.edit_message_text(
            t(context, "lang_set", name=get_lang_name(code, get_ui_lang(context))),
            reply_markup=main_menu_markup(context),
            parse_mode='Markdown',
        )

    elif data.startswith("ui_"):
        code = data.split("_", 1)[1]
        if code in UI_LANG_NAME:
            context.user_data['ui_lang'] = code
        await query.edit_message_text(
            t(context, "ui_set", name=UI_LANG_NAME[get_ui_lang(context)]),
            reply_markup=main_menu_markup(context),
            parse_mode='Markdown',
        )

    elif data == "menu_extract":
        context.user_data['mode'] = MODE_WAIT_FILE
        await query.edit_message_text(
            t(context, "extract_prompt",
              lang=get_lang_name(get_user_lang(context), get_ui_lang(context))),
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(t(context, "btn_home"), callback_data="menu_home")]]
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
            t(context, "tap_extract_first"),
            reply_markup=main_menu_markup(context),
            parse_mode='Markdown',
        )
        return

    fname = (doc.file_name or "file").lower()
    allowed = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".tif", ".webp", ".pdf")
    if not fname.endswith(allowed):
        await update.message.reply_text(t(context, "unsupported"))
        return

    if doc.file_size and doc.file_size > MAX_FILE_SIZE:
        await update.message.reply_text(t(context, "too_large", size=human_size(doc.file_size)))
        return

    chat_id = update.effective_chat.id
    lang = get_user_lang(context)
    ocr_lang_name = get_lang_name(lang, get_ui_lang(context))

    status = await update.message.reply_text(t(context, "extracting", lang=ocr_lang_name))

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
                text=t(context, "no_text"),
                reply_markup=main_menu_markup(context),
            )
            return

        if len(text) > 3500:
            buf = io.BytesIO(text.encode("utf-8"))
            base = os.path.splitext(doc.file_name or "extracted")[0]
            await context.bot.send_document(
                chat_id=chat_id,
                document=InputFile(buf, filename=f"{base}_text.txt"),
                caption=t(context, "extracted_caption", n=len(text)),
                reply_markup=main_menu_markup(context),
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=t(context, "extracted_inline", text=text),
                parse_mode='Markdown',
                reply_markup=main_menu_markup(context),
            )

    except Exception as e:
        logger.error(f"OCR failed: {e}")
        try:
            await status.delete()
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=chat_id,
            text=t(context, "ocr_failed", err=e),
            reply_markup=main_menu_markup(context),
        )
    finally:
        reset_user_state(context)


# ---------- OCR API call ----------

async def ocr_extract(file_bytes: bytes, filename: str, language: str, is_pdf: bool) -> str:
    timeout = aiohttp.ClientTimeout(total=90)
    data = aiohttp.FormData()
    data.add_field("file", file_bytes, filename=filename,
                   content_type="application/pdf" if is_pdf else "image/jpeg")
    data.add_field("language", language)
    data.add_field("isOverlayRequired", "false")
    data.add_field("detectOrientation", "true")
    data.add_field("scale", "true")
    data.add_field("OCREngine", "2")
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


# ---------- Health server ----------

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

    application = None
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
        if application is not None:
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
