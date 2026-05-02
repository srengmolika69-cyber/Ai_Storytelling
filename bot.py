import os
import sys
import json
import logging
from pathlib import Path

import google.generativeai as genai
from google.api_core.exceptions import PermissionDenied, InvalidArgument

# Load .env when running locally (Render injects env vars directly)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
# Optional owner fallback key — users can supply their own instead
DEFAULT_GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")

if not TELEGRAM_TOKEN:
    logger.critical("TELEGRAM_TOKEN is not set! Add it in Render Dashboard -> Environment.")
    sys.exit(1)

# ─── Persistent user-key store (JSON file) ───────────────────────────────────
# Render mounts a persistent disk at /data; fall back to local dir for dev
_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).parent
KEYS_FILE = _DATA_DIR / "user_keys.json"

def _load_keys() -> dict:
    if KEYS_FILE.exists():
        try:
            return json.loads(KEYS_FILE.read_text())
        except Exception:
            return {}
    return {}

def _save_keys(data: dict) -> None:
    KEYS_FILE.write_text(json.dumps(data, indent=2))

USER_KEYS: dict = _load_keys()   # { "user_id_str": "AIzaSy..." }

def get_user_key(user_id: int) -> str:
    return USER_KEYS.get(str(user_id), DEFAULT_GEMINI_KEY)

def set_user_key(user_id: int, key: str) -> None:
    USER_KEYS[str(user_id)] = key
    _save_keys(USER_KEYS)

def delete_user_key(user_id: int) -> bool:
    uid = str(user_id)
    if uid in USER_KEYS:
        del USER_KEYS[uid]
        _save_keys(USER_KEYS)
        return True
    return False

# ─── Conversation States ──────────────────────────────────────────────────────
CHOOSING_GENRE, TYPING_TOPIC, READING_STORY, WAITING_FOR_KEY = range(4)

# ─── Story Genres ─────────────────────────────────────────────────────────────
GENRES = {
    "folk":      ("🏮 រឿងនិទាន",     "Khmer folk tale / រឿងនិទានខ្មែរ"),
    "ghost":     ("👻 រឿងខ្មោច",     "Khmer ghost / horror story"),
    "love":      ("💕 រឿងស្នេហ៍",    "Khmer romantic love story"),
    "adventure": ("⚔️ រឿងផ្សងព្រេង", "Khmer adventure / hero story"),
    "fable":     ("🐘 រឿងសត្វ",      "Khmer animal fable with moral"),
    "legend":    ("🌟 រឿងព្រេង",     "Khmer legend / mythology"),
    "modern":    ("🏙️ រឿងទំនើប",    "Modern Khmer daily life story"),
    "children":  ("🌈 រឿងកុមារ",    "Khmer children bedtime story"),
}

SYSTEM_PROMPT = """អ្នកជាអ្នកនិទានរឿងខ្មែរដ៏ពូកែ និងជំនាញ។
សូមបង្កើតរឿងខ្មែរដែលមានគុណភាពខ្ពស់ ដោយប្រើភាសាខ្មែរសុទ្ធ វប្បធម៌ខ្មែរ
និងរចនាប័ទ្មនិទានរឿងប្រពៃណីខ្មែរ។

ក្បួននិទានរឿង:
- ចាប់ផ្តើមរឿងដោយបែបទាក់ទាញ
- ប្រើភាសាខ្មែរស្អាត ងាយយល់
- បន្ថែមស្មារតីខ្មែរ ទំនៀមទម្លាប់ ឬជំនឿ
- រឿងគួរមានអំណានពី ១០០-២០០ ពាក្យ
- បញ្ចប់ដោយសាររឿង ឬអត្ថន័យស្រស់ស្អាត
- គ្រប់ "ថ្នាក់" ទាំងអស់ត្រូវសរសេរជាទម្រង់ paragraph
"""

# ─── Keyboards ────────────────────────────────────────────────────────────────
def genre_keyboard() -> InlineKeyboardMarkup:
    keys = []
    items = list(GENRES.items())
    for i in range(0, len(items), 2):
        row = [InlineKeyboardButton(items[i][1][0], callback_data=f"genre:{items[i][0]}")]
        if i + 1 < len(items):
            row.append(InlineKeyboardButton(items[i+1][1][0], callback_data=f"genre:{items[i+1][0]}"))
        keys.append(row)
    return InlineKeyboardMarkup(keys)

def action_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 រឿងថ្មីទៀត",  callback_data="action:new"),
            InlineKeyboardButton("📖 ប្រភេទផ្សេង", callback_data="action:genres"),
        ],
        [InlineKeyboardButton("🏠 ទំព័រដើម", callback_data="action:home")],
    ])

def key_manage_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔑 ប្តូរ Key ថ្មី", callback_data="key:set"),
            InlineKeyboardButton("🗑️ លុប Key",        callback_data="key:delete"),
        ],
        [InlineKeyboardButton("◀️ ត្រឡប់", callback_data="key:back")],
    ])

# ─── Gemini ───────────────────────────────────────────────────────────────────
import asyncio
import google.generativeai as _genai_mod

def _call_gemini(api_key: str, prompt: str) -> str:
    """Run in a thread — avoids blocking the async event loop."""
    import google.generativeai as g
    g.configure(api_key=api_key)
    m = g.GenerativeModel("gemini-1.5-flash")
    return m.generate_content(prompt).text

async def generate_story(api_key: str, genre_desc: str, topic: str) -> str:
    if not api_key:
        return "⚠️ *គ្មាន API Key!*\nសូមប្រើ /setkey ដើម្បីដាក់ Gemini API Key ជាមុន។"
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"ប្រភេទរឿង: {genre_desc}\n"
        f"ប្រធានបទ: {topic}\n\n"
        f"សូមសរសេររឿងខ្មែរមួយពីប្រធានបទខាងលើ:"
    )
    try:
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, _call_gemini, api_key, prompt)
        return text
    except Exception as e:
        err = str(e).lower()
        logger.error(f"Gemini error: {e}")
        if "api_key" in err or "permission" in err or "invalid" in err or "credential" in err:
            return "🔑 *Gemini API Key មិនត្រឹមត្រូវ!*\nសូមប្រើ /setkey ដើម្បីដាក់ key ថ្មី។"
        if "quota" in err or "rate" in err or "429" in err:
            return "⏳ *Gemini free tier ផុត quota!*\nសូមរង់ចាំ ១ នាទី ហើយព្យាយាមម្តងទៀត។"
        return "❌ មានបញ្ហាក្នុងការបង្កើតរឿង។ សូមព្យាយាមម្តងទៀត។"

# ─── /start ───────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not get_user_key(user.id):
        await update.message.reply_text(
            f"🙏 សួស្តី *{user.first_name}*!\n\n"
            "🎭 *ស្វាគមន៍មកកាន់ Bot និទានរឿងខ្មែរ AI!*\n\n"
            "⚠️ Bot នេះប្រើ *Gemini API Key* របស់អ្នកផ្ទាល់។\n\n"
            "👉 *ជំហាន:*\n"
            "1\\. ទទួល key ឥតគិតថ្លៃ: [aistudio\\.google\\.com](https://aistudio.google.com/app/apikey)\n"
            "2\\. ប្រើ /setkey → វាយ key\n"
            "3\\. ចាប់ផ្តើមនិទានរឿង 🎉",
            parse_mode="MarkdownV2",
            disable_web_page_preview=True,
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"🙏 សួស្តី *{user.first_name}*!\n\n"
        "🎭 *ស្វាគមន៍មកកាន់ Bot និទានរឿងខ្មែរ AI!*\n\n"
        "សូមជ្រើសរើសប្រភេទរឿង ⬇️",
        parse_mode="Markdown",
        reply_markup=genre_keyboard(),
    )
    return CHOOSING_GENRE

# ─── /setkey flow ─────────────────────────────────────────────────────────────
async def setkey_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🔑 *ដាក់ Gemini API Key*\n\n"
        "សូមវាយ API Key របស់អ្នក:\n"
        "_\\(Key ចាប់ផ្តើមដោយ `AIzaSy...`\\)_\n\n"
        "ទទួល key ឥតគិតថ្លៃ: [aistudio\\.google\\.com](https://aistudio.google.com/app/apikey)\n\n"
        "⚠️ Bot នឹងលុប message ដែលមាន key ភ្លាម ដើម្បីសុវត្ថិភាព\\.\n\n"
        "/cancel ដើម្បីបោះបង់\\.",
        parse_mode="MarkdownV2",
        disable_web_page_preview=True,
    )
    return WAITING_FOR_KEY

async def receive_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    key = update.message.text.strip()
    user_id = update.effective_user.id

    # Delete the message immediately for security
    try:
        await update.message.delete()
    except Exception:
        pass

    if not key.startswith("AIza") or len(key) < 30:
        await update.message.reply_text(
            "❌ *Key មិនត្រឹមត្រូវ!*\n\n"
            "Key ត្រូវចាប់ផ្តើមដោយ `AIzaSy...`\n"
            "សូមព្យាយាមម្តងទៀត ឬ /cancel ដើម្បីបោះបង់។",
            parse_mode="Markdown",
        )
        return WAITING_FOR_KEY

    validating_msg = await update.message.reply_text(
        "⏳ *កំពុងត្រួតពិនិត្យ Key...*", parse_mode="Markdown"
    )
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _call_gemini, key, "hi")
        set_user_key(user_id, key)
        await validating_msg.edit_text(
            "✅ *API Key ត្រឹមត្រូវ! រក្សាទុករួចហើយ។*\n\n"
            "ប្រើ /story ដើម្បីចាប់ផ្តើមនិទានរឿង 🎭",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    except Exception as e:
        err = str(e).lower()
        logger.warning(f"Key validation error: {e}")
        if "api_key" in err or "permission" in err or "invalid" in err or "credential" in err:
            await validating_msg.edit_text(
                "❌ *Key នេះខុស ឬគ្មានសិទ្ធ!*\n\n"
                "សូមពិនិត្យ key ម្តងទៀត ឬបង្កើតថ្មី:\n"
                "[aistudio.google.com](https://aistudio.google.com/app/apikey)\n\n"
                "ព្យាយាមម្តងទៀត ឬ /cancel ដើម្បីបោះបង់។",
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
            return WAITING_FOR_KEY
        # Network/unknown error — save anyway and let user test
        set_user_key(user_id, key)
        await validating_msg.edit_text(
            "⚠️ *មិនអាចត្រួតពិនិត្យបាន — Key ត្រូវបានរក្សាទុក។*\n\n"
            "ប្រើ /story ដើម្បីសាកល្បង។",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

# ─── /mykey ───────────────────────────────────────────────────────────────────
async def mykey_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    personal_key = USER_KEYS.get(str(user_id))

    if personal_key:
        masked = personal_key[:8] + "••••••••" + personal_key[-4:]
        await update.message.reply_text(
            f"🔑 *API Key របស់អ្នក:*\n`{masked}`\n\n"
            "✅ Key ត្រូវបានរក្សាទុក\n\n"
            "សូមជ្រើសសកម្មភាព:",
            parse_mode="Markdown",
            reply_markup=key_manage_keyboard(),
        )
    else:
        await update.message.reply_text(
            "⚠️ *អ្នកមិនទាន់មាន API Key ទេ!*\n\n"
            "ប្រើ /setkey ដើម្បីដាក់ Gemini API Key\n"
            "ទទួល key ឥតគិតថ្លៃ: [aistudio.google.com](https://aistudio.google.com/app/apikey)",
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
    return ConversationHandler.END

async def key_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data.split(":")[1]
    user_id = query.from_user.id

    if action == "set":
        await query.edit_message_text(
            "🔑 *ដាក់ / ប្តូរ Gemini API Key*\n\n"
            "សូមវាយ key ថ្មី:\n"
            "_Key ចាប់ផ្តើមដោយ_ `AIzaSy...`\n\n"
            "⚠️ Bot នឹងលុប message ភ្លាម ដើម្បីសុវត្ថិភាព\n\n"
            "/cancel ដើម្បីបោះបង់",
            parse_mode="Markdown",
        )
        return WAITING_FOR_KEY

    elif action == "delete":
        if delete_user_key(user_id):
            await query.edit_message_text(
                "🗑️ *API Key ត្រូវបានលុបរួចហើយ!*\n\n"
                "ប្រើ /setkey ដើម្បីដាក់ key ថ្មី។",
                parse_mode="Markdown",
            )
        else:
            await query.edit_message_text("⚠️ គ្មាន Key ដើម្បីលុប។")
        return ConversationHandler.END

    elif action == "back":
        await query.edit_message_text(
            "◀️ ប្រើ /story ដើម្បីបន្ត ឬ /help ដើម្បីមើលជំនួយ។"
        )
        return ConversationHandler.END

    return ConversationHandler.END

# ─── Story flow ───────────────────────────────────────────────────────────────
async def story_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not get_user_key(user_id):
        await update.message.reply_text(
            "⚠️ *អ្នកមិនទាន់មាន API Key ទេ!*\n\n"
            "ប្រើ /setkey ដើម្បីដាក់ Gemini API Key ជាមុន\n"
            "ទទួល key ឥតគិតថ្លៃ: [aistudio.google.com](https://aistudio.google.com/app/apikey)",
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "📖 *ជ្រើសរើសប្រភេទរឿង:*",
        parse_mode="Markdown",
        reply_markup=genre_keyboard(),
    )
    return CHOOSING_GENRE

async def genre_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    genre_key = query.data.split(":")[1]
    genre_label, genre_desc = GENRES[genre_key]
    context.user_data["genre_label"] = genre_label
    context.user_data["genre_desc"] = genre_desc

    await query.edit_message_text(
        f"✅ ប្រភេទ: *{genre_label}*\n\n"
        "✍️ សូមវាយ *ប្រធានបទ* ឬ *ឈ្មោះតួអង្គ*:\n\n"
        "_ឧទាហរណ៍: កញ្ញាក្នុងព្រៃ, ក្មេងជិតទន្លេ, ស្នេហ៍ក្នុងភ្នំ..._",
        parse_mode="Markdown",
    )
    return TYPING_TOPIC

async def topic_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    topic = update.message.text.strip()
    user_id = update.effective_user.id
    genre_label = context.user_data.get("genre_label", "")
    genre_desc  = context.user_data.get("genre_desc", "")
    context.user_data["topic"] = topic

    api_key = get_user_key(user_id)
    if not api_key:
        await update.message.reply_text(
            "⚠️ *API Key ខ្វះ!* សូមប្រើ /setkey ជាមុន។", parse_mode="Markdown"
        )
        return ConversationHandler.END

    thinking_msg = await update.message.reply_text(
        f"🪄 *AI កំពុងនិទានរឿង...*\n\n"
        f"📖 ប្រភេទ: {genre_label}\n"
        f"🏷️ ប្រធានបទ: {topic}\n\n_សូមរង់ចាំ..._",
        parse_mode="Markdown",
    )
    story = await generate_story(api_key, genre_desc, topic)
    await thinking_msg.delete()

    await update.message.reply_text(
        f"📜 *រឿង: {topic}*\n"
        f"🏷️ {genre_label}\n{'─'*28}\n\n"
        f"{story}\n\n{'─'*28}\n"
        f"_✨ បង្កើតដោយ AI Khmer Storyteller_",
        parse_mode="Markdown",
        reply_markup=action_keyboard(),
    )
    return READING_STORY

async def action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data.split(":")[1]
    user_id = query.from_user.id

    if action == "new":
        genre_label = context.user_data.get("genre_label", "")
        genre_desc  = context.user_data.get("genre_desc", "")
        topic       = context.user_data.get("topic", "")
        api_key     = get_user_key(user_id)
        thinking_msg = await query.message.reply_text(
            "🪄 *AI កំពុងបង្កើតរឿងថ្មី...*", parse_mode="Markdown"
        )
        story = await generate_story(api_key, genre_desc, topic)
        await thinking_msg.delete()
        await query.message.reply_text(
            f"📜 *រឿងថ្មី: {topic}*\n"
            f"🏷️ {genre_label}\n{'─'*28}\n\n"
            f"{story}\n\n{'─'*28}\n"
            f"_✨ បង្កើតដោយ AI Khmer Storyteller_",
            parse_mode="Markdown",
            reply_markup=action_keyboard(),
        )
        return READING_STORY

    elif action == "genres":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "📖 *ជ្រើសរើសប្រភេទរឿង:*",
            parse_mode="Markdown",
            reply_markup=genre_keyboard(),
        )
        return CHOOSING_GENRE

    elif action == "home":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "🏠 *ទំព័រដើម*\n\n"
            "• /story — បង្កើតរឿង\n"
            "• /mykey — គ្រប់គ្រង API Key\n"
            "• /help — ជំនួយ",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    return READING_STORY

# ─── /help & /cancel ──────────────────────────────────────────────────────────
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📚 *របៀបប្រើ Bot*\n\n"
        "*ជំហាន:*\n"
        "1️⃣ ទទួល Gemini API Key ឥតគិតថ្លៃ:\n"
        "   [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)\n"
        "2️⃣ /setkey → វាយ key\n"
        "3️⃣ /story → ជ្រើសប្រភេទ → វាយប្រធានបទ\n"
        "4️⃣ ទទួលរឿង 🎉\n\n"
        "*ពាក្យបញ្ជា:*\n"
        "/start — ចាប់ផ្តើម\n"
        "/story — បង្កើតរឿង\n"
        "/setkey — ដាក់ / ប្តូរ API Key\n"
        "/mykey — មើល / លុប API Key\n"
        "/help — ជំនួយ\n"
        "/cancel — បោះបង់",
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("👋 បានបោះបង់! ប្រើ /start ឬ /story ដើម្បីបន្ត។")
    return ConversationHandler.END

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "❓ ខ្ញុំមិនយល់ពាក្យបញ្ជានេះ។\nប្រើ /help ដើម្បីមើលការណែនាំ។"
    )

# ─── Main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Key management conversation (handles /setkey + key:set callback)
    key_conv = ConversationHandler(
        entry_points=[
            CommandHandler("setkey", setkey_command),
            CallbackQueryHandler(key_callback_handler, pattern=r"^key:set$"),
        ],
        states={
            WAITING_FOR_KEY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_key)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    # Story conversation
    story_conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("story", story_command),
        ],
        states={
            CHOOSING_GENRE: [CallbackQueryHandler(genre_chosen,   pattern=r"^genre:")],
            TYPING_TOPIC:   [MessageHandler(filters.TEXT & ~filters.COMMAND, topic_received)],
            READING_STORY:  [CallbackQueryHandler(action_handler, pattern=r"^action:")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(key_conv)
    app.add_handler(story_conv)
    app.add_handler(CommandHandler("mykey", mykey_command))
    app.add_handler(CallbackQueryHandler(key_callback_handler, pattern=r"^key:"))
    app.add_handler(CommandHandler("help",  help_command))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    logger.info("Khmer Storytelling Bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
