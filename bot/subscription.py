import os
from datetime import datetime, timedelta

FREE_DAILY_LIMIT = 3
PREMIUM_DAILY_LIMIT = 999  # effectively unlimited
BONUS_PER_REFERRAL = 2

PLANS = {
    "free": {
        "name": "🆓 Bepul",
        "daily_limit": FREE_DAILY_LIMIT,
        "description": f"Kuniga {FREE_DAILY_LIMIT} ta hujjat",
    },
    "premium": {
        "name": "⭐ Premium",
        "daily_limit": PREMIUM_DAILY_LIMIT,
        "description": "Cheksiz hujjatlar",
    },
}


def get_admin_ids() -> set[int]:
    raw = os.environ.get("ADMIN_IDS", "")
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


def is_admin(user_id: int) -> bool:
    return user_id in get_admin_ids()


def get_daily_limit(plan: str) -> int:
    return PLANS.get(plan, PLANS["free"])["daily_limit"]


def check_limit(plan: str, used_today: int, bonus_docs: int = 0) -> dict:
    """
    Returns whether the user is allowed to generate a document.
    For free users: allowed if free quota remains OR bonus_docs > 0.
    using_bonus=True means the free quota is exhausted and a bonus doc will be consumed.
    """
    limit = get_daily_limit(plan)
    free_remaining = max(0, limit - used_today)
    using_bonus = (plan == "free") and free_remaining == 0 and bonus_docs > 0
    allowed = free_remaining > 0 or using_bonus or plan == "premium"
    return {
        "allowed": allowed,
        "used": used_today,
        "limit": limit,
        "free_remaining": free_remaining,
        "bonus_remaining": bonus_docs,
        "using_bonus": using_bonus,
    }


def parse_duration(text: str) -> str | None:
    """
    Parse a duration string like '30d', '1m', '1y' and return an expiry date string
    'YYYY-MM-DD', or None for lifetime.
    """
    text = text.strip().lower()
    if text in ("lifetime", "cheksiz", "forever"):
        return None
    if text.endswith("d") and text[:-1].isdigit():
        days = int(text[:-1])
    elif text.endswith("m") and text[:-1].isdigit():
        days = int(text[:-1]) * 30
    elif text.endswith("y") and text[:-1].isdigit():
        days = int(text[:-1]) * 365
    elif text.isdigit():
        days = int(text)
    else:
        return "invalid"

    expiry = datetime.now() + timedelta(days=days)
    return expiry.strftime("%Y-%m-%d")


def plan_status_text(plan_info: dict, used_today: int) -> str:
    plan = plan_info["plan"]
    cfg = PLANS.get(plan, PLANS["free"])
    limit = cfg["daily_limit"]
    free_remaining = max(0, limit - used_today)
    bonus_docs = plan_info.get("bonus_docs", 0)
    expires = plan_info.get("expires_at")

    lines = [
        f"<b>Sizning rejangiz:</b> {cfg['name']}\n",
        f"📊 <b>Bugungi foydalanish:</b> {used_today} / {'∞' if plan == 'premium' else limit}",
    ]

    if plan == "free":
        lines.append(f"🔢 <b>Kunlik qolgan:</b> {free_remaining} ta")
        if bonus_docs > 0:
            lines.append(f"🎁 <b>Bonus hujjatlar:</b> {bonus_docs} ta (do'stlar taklifi)")
        lines.append(
            "\n🛒 /buy — Premium xarid qiling (cheksiz hujjatlar)\n"
            "👥 /ref — Do'stlarni taklif qiling, bonus oling"
        )
    else:
        lines.append("✅ <b>Qolgan:</b> Cheksiz")
        if bonus_docs > 0:
            lines.append(f"🎁 <b>Bonus hujjatlar:</b> {bonus_docs} ta")
        if expires:
            lines.append(f"📅 <b>Muddati:</b> {expires} gacha")
        else:
            lines.append("📅 <b>Muddati:</b> Umrbod")

    return "\n".join(lines)
