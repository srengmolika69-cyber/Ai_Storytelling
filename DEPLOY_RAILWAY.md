# 🚂 Deploy to Railway — ការណែនាំពេញលេញ

## ជំហានទី ១ — Push Code ទៅ GitHub

```bash
# ក្នុង folder khmer_story_bot
git init
git add .
git commit -m "🎭 Initial Khmer Storytelling Bot"

# បង្កើត repo ថ្មីនៅ github.com → New repository
# បន្ទាប់មក:
git remote add origin https://github.com/YOUR_USERNAME/khmer-story-bot.git
git push -u origin main
```

---

## ជំហានទី ២ — បង្កើត Project នៅ Railway

1. ចូល **[railway.app](https://railway.app)** → ចុច **"Start a New Project"**
2. ជ្រើស **"Deploy from GitHub repo"**
3. ភ្ជាប់ GitHub account → ជ្រើស repo `khmer-story-bot`
4. Railway នឹង detect `Procfile` ដោយស្វ័យប្រវត្តិ ✅

---

## ជំហានទី ៣ — បន្ថែម Environment Variables

នៅក្នុង Railway dashboard:

```
Project → Service → Variables → "+ New Variable"
```

បន្ថែម **២ variables** ទាំងនេះ:

| Variable Name    | Value                        |
|-----------------|------------------------------|
| `TELEGRAM_TOKEN` | `1234567890:ABCdef...`       |
| `GEMINI_API_KEY` | `AIzaSy...`                  |

> ⚠️ **កុំ** commit `.env` file ទៅ GitHub — `.gitignore` ការពារហើយ

---

## ជំហានទី ៤ — Deploy!

1. Railway deploy ដោយស្វ័យប្រវត្តិ ✅
2. ចូលមើល **Logs** tab → ស្វែងរក:
   ```
   🎭 Khmer Storytelling Bot started!
   ```
3. បើឃើញ log នោះ = bot running 24/7! 🎉

---

## 🔁 Auto-Deploy (CI/CD)

រាល់ពេល `git push` ទៅ GitHub → Railway deploy ដោយស្វ័យប្រវត្តិ!

```bash
# ធ្វើការផ្លាស់ប្តូរ → push → Railway redeploy
git add .
git commit -m "✨ Update story prompt"
git push
```

---

## 💰 តម្លៃ Railway

| Plan    | Free Tier         | Hobby ($5/mo)     |
|---------|-------------------|-------------------|
| Hours   | 500 hrs/month     | Unlimited         |
| RAM     | 512 MB            | 8 GB              |
| Bot OK? | ✅ ~20 days/month | ✅ 24/7 always on |

> 💡 **Hobby plan ($5/mo)** ល្អបំផុតសម្រាប់ bot 24/7

---

## 🛠️ Troubleshooting

**Bot មិន start:**
```
# Check logs ក្នុង Railway → Logs tab
❌ TELEGRAM_TOKEN is not set!  → add variable
❌ GEMINI_API_KEY is not set!  → add variable
```

**Deploy failed:**
```bash
# Test locally ជាមុន:
pip install -r requirements.txt
python bot.py
```

**Bot slow / timeout:**
- Gemini free tier: 15 req/min → normal for small usage
- Upgrade to Gemini 1.5 Pro ប្រសិនបើត្រូវការ

---

_✨ Made with ❤️ for Khmer culture — Deployed on Railway_
