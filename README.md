# uzbek-doc-bot

  Telegram bot that generates academic documents in Uzbek using OpenAI GPT-4o-mini.

  ## Features
  - 📄 Referat (3–30 pages)
  - 📝 Mustaqil ish (5–40 pages)
  - 📋 Tezis (2–15 pages)
  - 🖼 Taqdimot — PowerPoint presentation (5–30 slides)
  - 📂 Document history with re-download
  - ⭐ Subscription system (Free 3/day · Premium unlimited)
  - 💳 Telegram Stars payments (75 / 175 / 299 stars)
  - 👥 Referral system — earn 2 bonus docs per invite
  - 📢 Admin broadcast to all users

  ## Setup

  ```bash
  pip install python-telegram-bot openai python-docx python-pptx aiofiles
  ```

  Required environment variables:
  ```
  TELEGRAM_BOT_TOKEN=...
  OPENAI_API_KEY=...
  ADMIN_IDS=123456789,987654321
  ```

  ```bash
  cd bot && python main.py
  ```

  ## Stack
  - Python 3.11
  - python-telegram-bot 20+
  - OpenAI GPT-4o-mini
  - SQLite (history, subscriptions, referrals)
  - python-docx + python-pptx
  