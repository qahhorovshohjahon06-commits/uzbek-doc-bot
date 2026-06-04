import logging
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, LabeledPrice
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode, ChatAction

from states import State
from ai_generator import (
    generate_content,
    QuotaExceededError, InvalidAPIKeyError, RateLimitedError, AIConnectionError,
)
from document_builder import build_docx, build_pptx
from database import (
    save_document, get_history, get_document,
    get_user_plan, set_user_plan, get_daily_count, get_all_users_stats, get_all_user_ids,
    register_referral, get_referral_stats, get_bonus_docs, use_bonus_doc,
    BONUS_PER_REFERRAL,
)
from subscription import (
    check_limit, plan_status_text, parse_duration,
    is_admin, PLANS,
)
from payments import PAYMENT_PLANS, STARS_CURRENCY, make_payload, parse_payload, build_invoice_prices

logger = logging.getLogger(__name__)

DOC_TYPES = {
    "referat":        {"label": "📄 Referat",      "name": "Referat",      "unit": "sahifa", "default": 10, "min": 3,  "max": 30},
    "mustaqil_ish":   {"label": "📝 Mustaqil ish", "name": "Mustaqil ish", "unit": "sahifa", "default": 15, "min": 5,  "max": 40},
    "tezis":          {"label": "📋 Tezis",        "name": "Tezis",        "unit": "sahifa", "default": 5,  "min": 2,  "max": 15},
    "presentation":   {"label": "🖼 Taqdimot",     "name": "Taqdimot",     "unit": "slayd",  "default": 10, "min": 5,  "max": 30},
}

DOC_TYPE_ICONS = {
    "referat": "📄", "mustaqil_ish": "📝", "tezis": "📋", "presentation": "🖼",
}

MAIN_MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📄 Referat"),    KeyboardButton("📝 Mustaqil ish")],
        [KeyboardButton("📋 Tezis"),      KeyboardButton("🖼 Taqdimot")],
        [KeyboardButton("ℹ️ Yordam"),     KeyboardButton("🏠 Bosh menyu")],
    ],
    resize_keyboard=True,
)

BUTTON_TO_TYPE = {
    "📄 Referat": "referat",
    "📝 Mustaqil ish": "mustaqil_ish",
    "📋 Tezis": "tezis",
    "🖼 Taqdimot": "presentation",
}


# ── Core commands ─────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user

    # Handle referral deep-link: /start ref_<referrer_id>
    if context.args and context.args[0].startswith("ref_"):
        try:
            referrer_id = int(context.args[0][4:])
            is_new = register_referral(referrer_id, user.id)
            if is_new:
                # Notify the referrer
                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=(
                            f"🎉 <b>Yangi do'st qo'shildi!</b>\n\n"
                            f"👤 {user.first_name} sizning taklifingiz orqali botga qo'shildi.\n"
                            f"🎁 Sizga <b>+{BONUS_PER_REFERRAL} bonus hujjat</b> berildi!"
                        ),
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass  # Referrer may have blocked the bot
        except (ValueError, IndexError):
            pass

    welcome = (
        f"Assalomu alaykum, {user.first_name}! 👋\n\n"
        "🤖 Men <b>AI Hujjat Yaratuvchi Bot</b>man.\n\n"
        "Men sizga o'zbek tilida quyidagi hujjatlarni yaratib beraman:\n\n"
        "📄 <b>Referat</b> — akademik referat\n"
        "📝 <b>Mustaqil ish</b> — mustaqil tadqiqot ishi\n"
        "📋 <b>Tezis</b> — ilmiy tezis\n"
        "🖼 <b>Taqdimot</b> — PowerPoint taqdimot\n\n"
        "📂 /history — Oldingi hujjatlar\n"
        "⭐ /plan — Rejam va limit\n"
        "🛒 /buy — Premium xarid qilish\n"
        "👥 /ref — Do'stlarni taklif qiling\n\n"
        "Quyidagi menyudan tanlang:"
    )
    await update.message.reply_text(welcome, parse_mode=ParseMode.HTML, reply_markup=MAIN_MENU_KEYBOARD)
    return State.CHOOSING_DOC_TYPE


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    help_text = (
        "ℹ️ <b>Bot haqida ma'lumot</b>\n\n"
        "Bu bot sun'iy intellekt yordamida o'zbek tilida hujjatlar yaratadi.\n\n"
        "<b>Qanday foydalanish:</b>\n"
        "1️⃣ Hujjat turini tanlang\n"
        "2️⃣ Mavzuni kiriting\n"
        "3️⃣ Sahifalar/slaydlar sonini kiriting\n"
        "4️⃣ Tayyor hujjatni yuklab oling\n\n"
        "<b>Hujjat turlari:</b>\n"
        "📄 Referat — 3–30 sahifa\n"
        "📝 Mustaqil ish — 5–40 sahifa\n"
        "📋 Tezis — 2–15 sahifa\n"
        "🖼 Taqdimot — 5–30 slayd\n\n"
        "<b>Buyruqlar:</b>\n"
        "/start — Bosh menyu\n"
        "/plan — Rejam va bugungi limit\n"
        "/buy — Premium xarid qilish ⭐\n"
        "/ref — Do'stlarni taklif qiling 👥\n"
        "/history — Oldingi hujjatlar\n"
        "/myid — Telegram ID ni ko'rish\n"
        "/cancel — Bekor qilish\n"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML, reply_markup=MAIN_MENU_KEYBOARD)
    return State.CHOOSING_DOC_TYPE


async def plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    plan_info = get_user_plan(user_id)
    used_today = get_daily_count(user_id)
    text = plan_status_text(plan_info, used_today)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=MAIN_MENU_KEYBOARD)


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    await update.message.reply_text(
        f"🆔 Sizning Telegram ID: <code>{uid}</code>\n\n"
        "Bu ID ni admin ga yuboring — premium aktivatsiya uchun kerak.\n"
        "Yoki /buy orqali to'g'ridan-to'g'ri xarid qiling ⭐",
        parse_mode=ParseMode.HTML,
    )


# ── Referral command ───────────────────────────────────────────────────────

async def ref_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user.id}"

    stats = get_referral_stats(user.id)
    total_referred = stats["referral_count"]
    bonus_docs = stats["bonus_docs"]
    total_earned = total_referred * BONUS_PER_REFERRAL

    text = (
        "👥 <b>Do'stlarni taklif qilish</b>\n\n"
        f"Har bir do'st uchun <b>+{BONUS_PER_REFERRAL} bonus hujjat</b> olasiz!\n"
        "Bonus hujjatlar kunlik limitdan tashqari ishlaydi.\n\n"
        f"🔗 <b>Sizning havolangiz:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"📊 <b>Statistika:</b>\n"
        f"  👤 Taklif qilinganlar: <b>{total_referred}</b> ta\n"
        f"  🎁 Bonus qozonilgan: <b>{total_earned}</b> ta\n"
        f"  ✅ Qolgan bonus: <b>{bonus_docs}</b> ta\n\n"
        "Havolani do'stlaringizga yuboring va ular bot ishlatganda "
        "avtomatik bonus olasiz! 🎉"
    )

    share_btn = InlineKeyboardButton(
        "📤 Do'stlarga yuborish",
        url=f"https://t.me/share/url?url={ref_link}&text=O%27zbek%20tilida%20referat%2C%20mustaqil%20ish%2C%20tezis%20va%20taqdimot%20yaratuvchi%20bot!",
    )
    copy_btn = InlineKeyboardButton("🔗 Havola nusxasi", callback_data=f"ref_copy:{user.id}")

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[share_btn], [copy_btn]]),
    )


async def ref_copy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Havola yuqorida ko'rsatilgan, nusxalang! 👆", show_alert=True)


# ── Payment handlers ───────────────────────────────────────────────────────

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    plan_info = get_user_plan(user_id)

    if plan_info["plan"] == "premium":
        expires = plan_info.get("expires_at")
        expiry_text = f"{expires} gacha" if expires else "Umrbod"
        await update.message.reply_text(
            f"⭐ Siz allaqachon <b>Premium</b> foydalanuvchisiz!\n"
            f"📅 Muddat: {expiry_text}\n\n"
            "Hujjat yaratishni davom ettiring 👇",
            parse_mode=ParseMode.HTML,
            reply_markup=MAIN_MENU_KEYBOARD,
        )
        return

    keyboard = []
    lines = ["⭐ <b>Premium rejani xarid qiling</b>\n\n"
             "Premium bilan:\n"
             "✅ Cheksiz hujjatlar — kunlik limitlar yo'q\n"
             "✅ Barcha hujjat turlari — referat, mustaqil ish, tezis, taqdimot\n"
             "✅ Yuqori sifatli AI generatsiya\n\n"
             "<b>Narxlar (Telegram Stars ⭐):</b>\n"]

    for key, plan in PAYMENT_PLANS.items():
        lines.append(f"  • {plan['label']} — <b>{plan['stars']} ⭐</b>")
        keyboard.append([
            InlineKeyboardButton(
                f"{plan['label']} — {plan['stars']} ⭐",
                callback_data=f"buy:{key}",
            )
        ])

    lines.append("\n👇 Rejalangizni tanlang:")
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def open_buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'open_buy' inline button from the limit-hit message."""
    query = update.callback_query
    await query.answer()
    # Reuse buy_command logic by faking an update with the query's message
    user_id = query.from_user.id
    plan_info = get_user_plan(user_id)

    keyboard = []
    lines = ["⭐ <b>Premium rejani xarid qiling</b>\n\n"
             "Premium bilan:\n"
             "✅ Cheksiz hujjatlar — kunlik limitlar yo'q\n"
             "✅ Barcha hujjat turlari\n"
             "✅ Yuqori sifatli AI generatsiya\n\n"
             "<b>Narxlar (Telegram Stars ⭐):</b>\n"]

    for key, plan in PAYMENT_PLANS.items():
        lines.append(f"  • {plan['label']} — <b>{plan['stars']} ⭐</b>")
        keyboard.append([
            InlineKeyboardButton(
                f"{plan['label']} — {plan['stars']} ⭐",
                callback_data=f"buy:{key}",
            )
        ])

    lines.append("\n👇 Rejalangizni tanlang:")
    await query.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def buy_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    plan_key = query.data.split(":")[1]
    plan = PAYMENT_PLANS.get(plan_key)
    if not plan:
        await query.message.reply_text("❌ Reja topilmadi.")
        return

    user_id = query.from_user.id
    payload = make_payload(plan_key, user_id)

    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=plan["label"],
        description=plan["description"],
        payload=payload,
        currency=STARS_CURRENCY,
        prices=build_invoice_prices(plan_key),
        provider_token="",
    )


async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.pre_checkout_query
    parsed = parse_payload(query.invoice_payload)

    if parsed is None:
        await query.answer(ok=False, error_message="Noto'g'ri to'lov ma'lumoti.")
        return

    duration, user_id = parsed
    if duration not in PAYMENT_PLANS:
        await query.answer(ok=False, error_message="Reja topilmadi.")
        return

    await query.answer(ok=True)


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    payment = update.message.successful_payment
    user_id = update.effective_user.id
    parsed = parse_payload(payment.invoice_payload)

    if parsed is None:
        logger.error(f"Invalid payment payload: {payment.invoice_payload}")
        return

    duration, paying_user_id = parsed

    # Safety check: payload user_id must match sender
    if paying_user_id != user_id:
        logger.warning(f"Payload user {paying_user_id} != sender {user_id}")

    plan = PAYMENT_PLANS.get(duration)
    if not plan:
        logger.error(f"Unknown plan duration: {duration}")
        return

    expires_at = None if duration == "lifetime" else __import__("subscription").parse_duration(duration)
    set_user_plan(user_id, "premium", expires_at, user_id)

    expiry_text = f"{expires_at} gacha" if expires_at else "Umrbod"
    stars = payment.total_amount

    logger.info(f"Premium activated for user {user_id}: {duration} ({stars} stars)")

    await update.message.reply_text(
        f"🎉 <b>To'lov muvaffaqiyatli!</b>\n\n"
        f"⭐ <b>Premium</b> faollashtirildi!\n"
        f"📅 Muddat: {expiry_text}\n"
        f"💫 To'langan: {stars} ⭐\n\n"
        "Endi cheksiz hujjatlar yaratishingiz mumkin!\n"
        "Quyidagi menyudan boshlang 👇",
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_MENU_KEYBOARD,
    )


# ── Admin commands ─────────────────────────────────────────────────────────

async def addpremium_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin_id = update.effective_user.id
    if not is_admin(admin_id):
        await update.message.reply_text("❌ Bu buyruq faqat adminlar uchun.")
        return

    args = context.args
    if len(args) < 1:
        await update.message.reply_text(
            "Foydalanish:\n"
            "<code>/addpremium &lt;user_id&gt; [muddat]</code>\n\n"
            "Muddat misollari:\n"
            "  <code>30d</code> — 30 kun\n"
            "  <code>3m</code>  — 3 oy\n"
            "  <code>1y</code>  — 1 yil\n"
            "  <code>lifetime</code> — umrbod\n\n"
            "Misol: <code>/addpremium 123456789 30d</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    if not args[0].lstrip("-").isdigit():
        await update.message.reply_text("❌ User ID raqam bo'lishi kerak.")
        return

    target_id = int(args[0])
    duration_str = args[1] if len(args) >= 2 else "lifetime"
    expires_at = parse_duration(duration_str)

    if expires_at == "invalid":
        await update.message.reply_text(
            "❌ Noto'g'ri muddat formati.\n"
            "Misol: <code>30d</code>, <code>3m</code>, <code>1y</code>, <code>lifetime</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    set_user_plan(target_id, "premium", expires_at, admin_id)

    expiry_text = f"{expires_at} gacha" if expires_at else "Umrbod"
    await update.message.reply_text(
        f"✅ <b>Premium faollashtirildi!</b>\n\n"
        f"👤 User ID: <code>{target_id}</code>\n"
        f"⭐ Reja: Premium\n"
        f"📅 Muddat: {expiry_text}",
        parse_mode=ParseMode.HTML,
    )


async def removepremium_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin_id = update.effective_user.id
    if not is_admin(admin_id):
        await update.message.reply_text("❌ Bu buyruq faqat adminlar uchun.")
        return

    args = context.args
    if not args or not args[0].lstrip("-").isdigit():
        await update.message.reply_text(
            "Foydalanish: <code>/removepremium &lt;user_id&gt;</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    target_id = int(args[0])
    set_user_plan(target_id, "free", None, admin_id)
    await update.message.reply_text(
        f"✅ User <code>{target_id}</code> rejasi <b>Bepul</b> ga qaytarildi.",
        parse_mode=ParseMode.HTML,
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin_id = update.effective_user.id
    if not is_admin(admin_id):
        await update.message.reply_text("❌ Bu buyruq faqat adminlar uchun.")
        return

    rows = get_all_users_stats()
    if not rows:
        await update.message.reply_text("Hali hech kim hujjat yaratmagan.")
        return

    lines = [f"📊 <b>Foydalanuvchilar statistikasi</b> ({len(rows)} ta):\n"]
    for r in rows[:20]:
        icon = "⭐" if r["plan"] == "premium" else "🆓"
        exp = f" ({r['expires_at']} gacha)" if r["expires_at"] else ""
        lines.append(f"{icon} <code>{r['user_id']}</code> — {r['total_docs']} hujjat{exp}")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /broadcast <text>
    Sends a message to every known user. Admin-only.
    Supports HTML formatting. Reports delivered/failed counts.
    """
    admin_id = update.effective_user.id
    if not is_admin(admin_id):
        await update.message.reply_text("❌ Bu buyruq faqat adminlar uchun.")
        return

    if not context.args:
        await update.message.reply_text(
            "Foydalanish: <code>/broadcast &lt;xabar matni&gt;</code>\n\n"
            "HTML teglari qo'llab-quvvatlanadi: &lt;b&gt;, &lt;i&gt;, &lt;code&gt;, &lt;a href=...&gt;",
            parse_mode=ParseMode.HTML,
        )
        return

    message_text = " ".join(context.args)
    user_ids = get_all_user_ids()

    if not user_ids:
        await update.message.reply_text("Hali hech qanday foydalanuvchi yo'q.")
        return

    status_msg = await update.message.reply_text(
        f"📤 Xabar yuborilmoqda... (0 / {len(user_ids)})",
    )

    delivered = 0
    failed = 0
    blocked = 0

    for i, uid in enumerate(user_ids, 1):
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=message_text,
                parse_mode=ParseMode.HTML,
            )
            delivered += 1
        except Exception as e:
            err = str(e).lower()
            if "blocked" in err or "deactivated" in err or "chat not found" in err:
                blocked += 1
            else:
                failed += 1

        # Update progress every 20 users
        if i % 20 == 0 or i == len(user_ids):
            try:
                await status_msg.edit_text(
                    f"📤 Xabar yuborilmoqda... ({i} / {len(user_ids)})"
                )
            except Exception:
                pass

    await status_msg.edit_text(
        f"✅ <b>Broadcast tugadi!</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{len(user_ids)}</b>\n"
        f"✅ Yetkazildi: <b>{delivered}</b>\n"
        f"🚫 Bot bloklangan/o'chirilgan: <b>{blocked}</b>\n"
        f"❌ Boshqa xatolar: <b>{failed}</b>",
        parse_mode=ParseMode.HTML,
    )


# ── History ────────────────────────────────────────────────────────────────

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    rows = get_history(user_id)

    if not rows:
        await update.message.reply_text(
            "📂 <b>Tarix bo'sh</b>\n\n"
            "Siz hali hech qanday hujjat yaratmadingiz.\n"
            "Yangi hujjat yaratish uchun menyudan tanlang 👇",
            parse_mode=ParseMode.HTML,
            reply_markup=MAIN_MENU_KEYBOARD,
        )
        return

    lines = ["📂 <b>Sizning hujjatlaringiz</b> (oxirgi 10 ta):\n"]
    keyboard = []

    for row in rows:
        icon = DOC_TYPE_ICONS.get(row["doc_type"], "📄")
        cfg = DOC_TYPES.get(row["doc_type"], {})
        unit = cfg.get("unit", "sahifa")
        lines.append(
            f"{icon} <b>{row['topic'][:35]}</b>\n"
            f"   {cfg.get('name', row['doc_type'])} • {row['count']} {unit} • {row['created_at']}"
        )
        keyboard.append([
            InlineKeyboardButton(
                f"{icon} {row['topic'][:30]} ({row['created_at']})",
                callback_data=f"dl:{row['id']}",
            )
        ])

    lines.append("\n⬇️ Yuklab olish uchun bosing:")
    await update.message.reply_text(
        "\n\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if not data.startswith("dl:"):
        return

    doc_id = int(data.split(":")[1])
    row = get_document(doc_id, user_id)

    if not row:
        await query.message.reply_text("❌ Hujjat topilmadi yoki o'chirilgan.")
        return

    await query.message.chat.send_action(ChatAction.UPLOAD_DOCUMENT)

    file_buffer = io.BytesIO(row["file_data"])
    cfg = DOC_TYPES.get(row["doc_type"], {})
    icon = DOC_TYPE_ICONS.get(row["doc_type"], "📄")

    caption = (
        f"{icon} <b>{cfg.get('name', row['doc_type'])}</b>\n\n"
        f"📌 Mavzu: {row['topic']}\n"
        f"📅 Yaratilgan: {row['created_at']}"
    )

    await query.message.reply_document(
        document=io.BufferedReader(file_buffer),
        filename=row["filename"],
        caption=caption,
        parse_mode=ParseMode.HTML,
    )


# ── Conversation handlers ──────────────────────────────────────────────────

async def choose_doc_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()

    if text == "ℹ️ Yordam":
        return await help_command(update, context)
    if text == "🏠 Bosh menyu":
        return await start(update, context)

    doc_type = BUTTON_TO_TYPE.get(text)
    if not doc_type:
        await update.message.reply_text(
            "Iltimos, quyidagi menyudan tanlang 👇",
            reply_markup=MAIN_MENU_KEYBOARD,
        )
        return State.CHOOSING_DOC_TYPE

    # ── Limit check ──
    user_id = update.effective_user.id
    plan_info = get_user_plan(user_id)
    used_today = get_daily_count(user_id)
    bonus_docs = plan_info.get("bonus_docs", 0)
    result = check_limit(plan_info["plan"], used_today, bonus_docs)

    if not result["allowed"]:
        await update.message.reply_text(
            "🚫 <b>Kunlik limitga yetdingiz!</b>\n\n"
            f"📊 Bugun: {result['used']} / {result['limit']} ta hujjat\n\n"
            "⭐ <b>Premium</b> rejaga o'ting — cheksiz hujjatlar yarating!\n"
            "👥 Yoki do'stlarni taklif qiling, bonus oling: /ref",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⭐ Premium xarid qilish", callback_data="open_buy"),
                InlineKeyboardButton("👥 Do'stlarni taklif qilish", callback_data="open_ref"),
            ]]),
        )
        return State.CHOOSING_DOC_TYPE

    cfg = DOC_TYPES[doc_type]
    context.user_data["doc_type"] = doc_type

    remaining_text = ""
    if plan_info["plan"] == "free":
        if result["using_bonus"]:
            remaining_text = f"\n\n🎁 Bonus hujjat ishlatilmoqda (qolgan: {result['bonus_remaining'] - 1} ta)"
        else:
            remaining_text = f"\n\n🔢 Bugungi qolgan: <b>{result['free_remaining'] - 1}</b> ta (bu hujjatdan keyin)"

    await update.message.reply_text(
        f"{cfg['label']} tanlandi!\n\n"
        f"✏️ Iltimos, <b>mavzuni</b> kiriting:\n\n"
        f"<i>Misol: \"Ekologiya va atrof-muhit muammolari\"</i>"
        f"{remaining_text}",
        parse_mode=ParseMode.HTML,
    )
    return State.ENTERING_TOPIC


async def enter_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()

    if text in BUTTON_TO_TYPE or text in ("ℹ️ Yordam", "🏠 Bosh menyu"):
        await update.message.reply_text("Avval mavzuni kiriting yoki /cancel buyrug'ini yuboring.")
        return State.ENTERING_TOPIC

    if len(text) < 3:
        await update.message.reply_text("Mavzu juda qisqa. Iltimos, to'liqroq yozing.")
        return State.ENTERING_TOPIC

    context.user_data["topic"] = text
    doc_type = context.user_data["doc_type"]
    cfg = DOC_TYPES[doc_type]

    await update.message.reply_text(
        f"📌 Mavzu: <b>{text}</b>\n\n"
        f"🔢 Nechta <b>{cfg['unit']}</b> kerak?\n"
        f"<i>(Min: {cfg['min']}, Max: {cfg['max']}, tavsiya: {cfg['default']})</i>",
        parse_mode=ParseMode.HTML,
    )
    return State.ENTERING_COUNT


async def enter_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()

    if text in BUTTON_TO_TYPE or text in ("ℹ️ Yordam", "🏠 Bosh menyu"):
        await update.message.reply_text("Avval sonni kiriting yoki /cancel buyrug'ini yuboring.")
        return State.ENTERING_COUNT

    try:
        count = int(text)
    except ValueError:
        await update.message.reply_text("Iltimos, faqat raqam kiriting. Masalan: 10")
        return State.ENTERING_COUNT

    doc_type = context.user_data["doc_type"]
    cfg = DOC_TYPES[doc_type]

    if count < cfg["min"] or count > cfg["max"]:
        await update.message.reply_text(
            f"Son {cfg['min']} va {cfg['max']} orasida bo'lishi kerak.\nIltimos qayta kiriting:"
        )
        return State.ENTERING_COUNT

    context.user_data["count"] = count
    topic = context.user_data["topic"]

    await update.message.reply_text(
        f"⏳ <b>Yaratilmoqda...</b>\n\n"
        f"📌 Mavzu: {topic}\n"
        f"📊 {cfg['unit'].capitalize()}: {count}\n\n"
        f"Bu biroz vaqt olishi mumkin, iltimos kuting...",
        parse_mode=ParseMode.HTML,
    )

    await update.message.chat.send_action(ChatAction.UPLOAD_DOCUMENT)

    try:
        content = await generate_content(doc_type, topic, count)
        user_id = update.effective_user.id

        if doc_type == "presentation":
            file_buffer = build_pptx(topic, content)
            filename = f"{topic[:40].replace(' ', '_')}_taqdimot.pptx"
            file_bytes = file_buffer.getvalue()
            caption = (
                f"✅ <b>Taqdimot tayyor!</b>\n\n"
                f"📌 Mavzu: {topic}\n"
                f"🖼 Slaydlar: {count} ta\n\n"
                "PowerPoint formatida yuborildi."
            )
            await update.message.reply_document(
                document=io.BufferedReader(io.BytesIO(file_bytes)),
                filename=filename,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
        else:
            file_buffer = build_docx(topic, content, doc_type)
            filename = f"{topic[:40].replace(' ', '_')}_{doc_type}.docx"
            file_bytes = file_buffer.getvalue()
            caption = (
                f"✅ <b>{cfg['name']} tayyor!</b>\n\n"
                f"📌 Mavzu: {topic}\n"
                f"📄 {cfg['unit'].capitalize()}: {count} ta\n\n"
                "Word formatida yuborildi."
            )
            await update.message.reply_document(
                document=io.BufferedReader(io.BytesIO(file_bytes)),
                filename=filename,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )

        save_document(user_id, doc_type, topic, count, filename, file_bytes)

        # Show remaining limit for free users
        plan_info = get_user_plan(user_id)
        used_today = get_daily_count(user_id)
        bonus_docs_now = plan_info.get("bonus_docs", 0)
        limit_result = check_limit(plan_info["plan"], used_today, bonus_docs_now)

        # Deduct bonus doc if one was consumed (free quota exhausted before this doc)
        if plan_info["plan"] == "free" and (used_today - 1) >= limit_result["limit"]:
            use_bonus_doc(user_id)
            bonus_docs_now = max(0, bonus_docs_now - 1)

        if plan_info["plan"] == "free":
            free_left = limit_result["free_remaining"]
            bonus_left = bonus_docs_now
            if free_left == 0 and bonus_left == 0:
                await update.message.reply_text(
                    "Yana hujjat yaratishni xohlaysizmi? Quyidagi menyudan tanlang 👇\n\n"
                    f"🚫 Bugungi limit tugadi.\n"
                    "Ertaga yangilanadi yoki premium/bonus oling ⭐",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("⭐ Premium xarid qilish", callback_data="open_buy"),
                        InlineKeyboardButton("👥 Do'st taklif qilish", callback_data="open_ref"),
                    ]]),
                )
            elif free_left > 0:
                await update.message.reply_text(
                    "Yana hujjat yaratishni xohlaysizmi? Quyidagi menyudan tanlang 👇\n\n"
                    f"🔢 Bugungi qolgan: <b>{free_left}</b> ta"
                    + (f"  |  🎁 Bonus: <b>{bonus_left}</b> ta" if bonus_left > 0 else ""),
                    parse_mode=ParseMode.HTML,
                    reply_markup=MAIN_MENU_KEYBOARD,
                )
            else:
                await update.message.reply_text(
                    "Yana hujjat yaratishni xohlaysizmi? Quyidagi menyudan tanlang 👇\n\n"
                    f"🎁 Bonus qolgan: <b>{bonus_left}</b> ta",
                    parse_mode=ParseMode.HTML,
                    reply_markup=MAIN_MENU_KEYBOARD,
                )
        else:
            await update.message.reply_text(
                "Yana hujjat yaratishni xohlaysizmi? Quyidagi menyudan tanlang 👇\n\n"
                "⭐ Premium — cheksiz foydalanish",
                parse_mode=ParseMode.HTML,
                reply_markup=MAIN_MENU_KEYBOARD,
            )

    except QuotaExceededError:
        logger.error("OpenAI quota exceeded — account has no credits")
        await update.message.reply_text(
            "⚠️ <b>AI xizmatida muammo</b>\n\n"
            "OpenAI hisobidagi kredit tugagan. Iltimos, keyinroq urinib ko'ring.\n\n"
            "Agar admin bo'lsangiz: <a href='https://platform.openai.com/settings/organization/billing'>openai.com/billing</a> da kreditni to'ldiring.",
            parse_mode=ParseMode.HTML,
            reply_markup=MAIN_MENU_KEYBOARD,
        )

    except InvalidAPIKeyError:
        logger.error("OpenAI API key is missing or invalid")
        await update.message.reply_text(
            "⚠️ <b>AI xizmatiga ulanib bo'lmadi</b>\n\n"
            "API kalit noto'g'ri yoki o'rnatilmagan. Admin bilan bog'laning.",
            parse_mode=ParseMode.HTML,
            reply_markup=MAIN_MENU_KEYBOARD,
        )

    except RateLimitedError:
        logger.warning("OpenAI rate limit hit")
        await update.message.reply_text(
            "⏳ <b>So'rovlar juda ko'p</b>\n\n"
            "Hozir AI band. Bir necha soniyadan so'ng qayta urinib ko'ring.",
            parse_mode=ParseMode.HTML,
            reply_markup=MAIN_MENU_KEYBOARD,
        )

    except AIConnectionError:
        logger.error("OpenAI connection error")
        await update.message.reply_text(
            "🌐 <b>Tarmoq xatosi</b>\n\n"
            "AI serveriga ulanishda muammo. Iltimos qayta urinib ko'ring.",
            parse_mode=ParseMode.HTML,
            reply_markup=MAIN_MENU_KEYBOARD,
        )

    except Exception as e:
        logger.error(f"Unexpected error generating document: {e}")
        await update.message.reply_text(
            "❌ <b>Kutilmagan xatolik</b>\n\n"
            "Iltimos qayta urinib ko'ring yoki /start buyrug'ini yuboring.",
            parse_mode=ParseMode.HTML,
            reply_markup=MAIN_MENU_KEYBOARD,
        )

    return State.CHOOSING_DOC_TYPE


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Bekor qilindi. Bosh menyuga qaytildi.",
        reply_markup=MAIN_MENU_KEYBOARD,
    )
    return State.CHOOSING_DOC_TYPE


async def open_ref_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'open_ref' inline button — shows referral info inline."""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user.id}"
    stats = get_referral_stats(user.id)

    text = (
        "👥 <b>Do'stlarni taklif qilish</b>\n\n"
        f"Har bir do'st uchun <b>+{BONUS_PER_REFERRAL} bonus hujjat</b> olasiz!\n\n"
        f"🔗 <b>Sizning havolangiz:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"👤 Taklif qilinganlar: <b>{stats['referral_count']}</b> ta\n"
        f"🎁 Qolgan bonus: <b>{stats['bonus_docs']}</b> ta"
    )
    share_btn = InlineKeyboardButton(
        "📤 Do'stlarga yuborish",
        url=f"https://t.me/share/url?url={ref_link}&text=O%27zbek%20tilida%20hujjat%20yaratuvchi%20bot!",
    )
    await query.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[share_btn]]),
    )


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Tushunmadim. Iltimos menyudan tanlang 👇",
        reply_markup=MAIN_MENU_KEYBOARD,
    )
