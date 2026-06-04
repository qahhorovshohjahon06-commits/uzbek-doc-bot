from telegram import LabeledPrice

# Telegram Stars currency code
STARS_CURRENCY = "XTR"

# Premium plans available for purchase
# amount is in Stars (1 unit = 1 Star)
PAYMENT_PLANS = {
    "30d": {
        "label": "⭐ Premium — 30 kun",
        "description": "30 kunlik cheksiz hujjat yaratish huquqi",
        "duration": "30d",
        "duration_text": "30 kun",
        "stars": 75,
    },
    "90d": {
        "label": "⭐ Premium — 90 kun",
        "description": "90 kunlik cheksiz hujjat yaratish huquqi",
        "duration": "90d",
        "duration_text": "90 kun",
        "stars": 175,
    },
    "lifetime": {
        "label": "⭐ Premium — Umrbod",
        "description": "Umrbod cheksiz hujjat yaratish huquqi",
        "duration": "lifetime",
        "duration_text": "Umrbod",
        "stars": 299,
    },
}

PAYLOAD_PREFIX = "premium_"


def make_payload(duration: str, user_id: int) -> str:
    return f"{PAYLOAD_PREFIX}{duration}_{user_id}"


def parse_payload(payload: str) -> tuple[str, int] | None:
    """Returns (duration, user_id) or None if invalid."""
    if not payload.startswith(PAYLOAD_PREFIX):
        return None
    rest = payload[len(PAYLOAD_PREFIX):]
    parts = rest.rsplit("_", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        return None
    return parts[0], int(parts[1])


def build_invoice_prices(plan_key: str) -> list[LabeledPrice]:
    plan = PAYMENT_PLANS[plan_key]
    return [LabeledPrice(plan["label"], plan["stars"])]
