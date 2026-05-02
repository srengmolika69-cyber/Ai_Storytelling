# 🎭 AI Khmer Storytelling Telegram Bot

Bot Telegram ដែលប្រើ AI Gemini សម្រាប់និទានរឿងខ្មែរ!

## ✨ លក្ខណៈពិសេស

- 🏮 រឿងនិទាន (Folk Tales)
- 👻 រឿងខ្មោច (Ghost Stories)
- 💕 រឿងស្នេហ៍ (Love Stories)
- ⚔️ រឿងផ្សងព្រេង (Adventures)
- 🐘 រឿងសត្វ (Fables)
- 🌟 រឿងព្រេង (Legends)
- 🏙️ រឿងទំនើប (Modern Stories)
- 🌈 រឿងកុមារ (Children's Stories)

## 🚀 របៀបដំណើរការ

### ជំហានទី ១: ទទួល API Keys

**Telegram Bot Token:**
1. បើក Telegram → ស្វែងរក `@BotFather`
2. វាយ `/newbot` → ដាក់ឈ្មោះ bot
3. ចម្លង token ដែលបានទទួល

**Gemini API Key (FREE):**
1. ចូល [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. ចុច "Create API Key"
3. ចម្លង key (free tier ៖ 15 requests/min, 1500/day)

### ជំហានទី ២: Setup Project

```bash
# Clone / download files
cd khmer_story_bot

# Create virtual environment
python -m venv venv
source venv/bin/activate      # Linux/Mac
# venv\Scripts\activate       # Windows

# Install dependencies
pip install -r requirements.txt

# Setup environment variables
cp .env.example .env
# Edit .env and fill in your keys
```

### ជំហានទី ៣: Configure .env

```env
TELEGRAM_TOKEN=1234567890:ABCdef...
GEMINI_API_KEY=AIzaSy...
```

### ជំហានទី ៤: Run Bot

```bash
python bot.py
```

## 📱 ពាក្យបញ្ជា Bot

| Command | អត្ថន័យ |
|---------|---------|
| `/start` | ចាប់ផ្តើមប្រើ bot |
| `/story` | បង្កើតរឿងថ្មី |
| `/help` | មើលជំនួយ |
| `/cancel` | បោះបង់ |

## 🌐 Deploy (Optional)

**ដំណើរការ 24/7 ដោយឥតគិតថ្លៃ:**

```bash
# Railway.app
railway init
railway add
railway deploy

# ឬ Render.com
# ឬ Fly.io
```

## 📦 Tech Stack

- `python-telegram-bot` v21 — Telegram Bot SDK
- `google-generativeai` — Gemini 1.5 Flash (free tier)
- Python 3.10+

## 💡 Gemini Free Tier Limits

| Metric | Limit |
|--------|-------|
| Requests/minute | 15 RPM |
| Requests/day | 1,500 RPD |
| Tokens/minute | 1M TPM |

Free tier គ្រប់គ្រាន់សម្រាប់ personal bot!

---
_✨ Made with ❤️ for Khmer culture_
