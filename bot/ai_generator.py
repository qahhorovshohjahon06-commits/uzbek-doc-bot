import os
import logging
from openai import AsyncOpenAI, APIStatusError, APIConnectionError, AuthenticationError, RateLimitError

logger = logging.getLogger(__name__)

MODEL = "llama-3.1-70b-versatile"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


# ── Typed exceptions ────────────────────────────────────────────────────────

class QuotaExceededError(Exception):
    """Groq account quota or rate limit exceeded."""

class InvalidAPIKeyError(Exception):
    """GROQ_API_KEY is missing or invalid."""

class RateLimitedError(Exception):
    """Too many requests — temporary rate limit."""

class AIConnectionError(Exception):
    """Network error reaching Groq."""


# ── Client factory (lazy — bot starts even without the key set) ─────────────

def _get_client() -> AsyncOpenAI:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        logger.error("GROQ_API_KEY environment variable is not set!")
        raise InvalidAPIKeyError("GROQ_API_KEY is not configured")
    return AsyncOpenAI(api_key=api_key, base_url=GROQ_BASE_URL)


# ── Prompts ─────────────────────────────────────────────────────────────────

PROMPTS = {
    "referat": {
        "system": "Siz o'zbek tilida akademik referat yozuvchi mutaxasssissiz. Barcha matnlar to'liq o'zbek tilida bo'lishi kerak.",
        "user": lambda topic, pages: (
            f"Mavzu: {topic}\n\n"
            f"O'zbek tilida {pages} sahifalik akademik referat yozing.\n"
            "Tarkib:\n"
            "1. Kirish (mavzuning dolzarbligi)\n"
            "2. Asosiy qism (2-3 bo'lim, har biri batafsil)\n"
            "3. Xulosa\n"
            "4. Foydalanilgan adabiyotlar\n\n"
            "Iltimos, to'liq, sifatli va professional referat yozing."
        ),
    },
    "mustaqil_ish": {
        "system": "Siz o'zbek tilida mustaqil ish yozuvchi akademik mutaxassississiz. Barcha matnlar to'liq o'zbek tilida bo'lishi kerak.",
        "user": lambda topic, pages: (
            f"Mavzu: {topic}\n\n"
            f"O'zbek tilida {pages} sahifalik mustaqil ish yozing.\n"
            "Tarkib:\n"
            "1. Annotatsiya\n"
            "2. Kirish\n"
            "3. Nazariy asos\n"
            "4. Tahlil va muhokama\n"
            "5. Amaliy qism\n"
            "6. Xulosa va takliflar\n"
            "7. Adabiyotlar ro'yxati\n\n"
            "Professional va to'liq mustaqil ish tayyorlang."
        ),
    },
    "tezis": {
        "system": "Siz o'zbek tilida ilmiy tezis yozuvchi mutaxasssissiz. Barcha matnlar to'liq o'zbek tilida bo'lishi kerak.",
        "user": lambda topic, pages: (
            f"Mavzu: {topic}\n\n"
            f"O'zbek tilida {pages} sahifalik ilmiy tezis yozing.\n"
            "Tarkib:\n"
            "1. Tezis sarlavhasi va muallif ma'lumotlari (to'ldiring)\n"
            "2. Annotatsiya (o'zbek va ingliz tillarida)\n"
            "3. Kirish: Muammo dolzarbligi\n"
            "4. Tadqiqot maqsadi va vazifalari\n"
            "5. Asosiy natijalar\n"
            "6. Xulosa\n"
            "7. Adabiyotlar\n\n"
            "Ilmiy uslubda, qisqa va lo'nda tezis tayyorlang."
        ),
    },
    "presentation": {
        "system": "Siz o'zbek tilida taqdimot mazmunini yozuvchi mutaxasssissiz. Barcha matnlar o'zbek tilida bo'lishi kerak.",
        "user": lambda topic, slides: (
            f"Mavzu: {topic}\n\n"
            f"O'zbek tilida {slides} ta slaydli taqdimot mazmunini yozing.\n"
            "Har bir slayd uchun quyidagi formatda yozing:\n"
            "SLAYD [raqam]: [Sarlavha]\n"
            "- [asosiy fikr 1]\n"
            "- [asosiy fikr 2]\n"
            "- [asosiy fikr 3]\n\n"
            "1-slayd: Muqova (mavzu va muallif)\n"
            f"2-{slides-1}-slaydlar: Asosiy mazmun\n"
            f"{slides}-slayd: Xulosa\n\n"
            "Har bir slaydda 3-5 ta qisqa, aniq fikr bo'lsin."
        ),
    },
}


# ── Generator ───────────────────────────────────────────────────────────────

async def generate_content(doc_type: str, topic: str, count: int) -> str:
    client = _get_client()  # raises InvalidAPIKeyError if key missing

    prompt_cfg = PROMPTS[doc_type]
    system_msg = prompt_cfg["system"]
    user_msg = prompt_cfg["user"](topic, count)

    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=4000,
            temperature=0.7,
        )
        return response.choices[0].message.content

    except AuthenticationError as e:
        logger.error(f"Groq auth error: {e}")
        raise InvalidAPIKeyError(str(e)) from e

    except RateLimitError as e:
        msg = str(e).lower()
        logger.error(f"Groq rate/quota error: {e}")
        if "insufficient_quota" in msg or "exceeded your current quota" in msg or "rate_limit" in msg:
            raise QuotaExceededError(str(e)) from e
        raise RateLimitedError(str(e)) from e

    except APIConnectionError as e:
        logger.error(f"Groq connection error: {e}")
        raise AIConnectionError(str(e)) from e

    except APIStatusError as e:
        logger.error(f"Groq API error {e.status_code}: {e}")
        if e.status_code == 429:
            raise QuotaExceededError(str(e)) from e
        raise
