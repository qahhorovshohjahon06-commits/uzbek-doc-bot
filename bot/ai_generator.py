import os
import logging
from openai import AsyncOpenAI, APIStatusError, APIConnectionError, AuthenticationError, RateLimitError

logger = logging.getLogger(__name__)

_api_key = os.environ.get("OPENAI_API_KEY", "")
if not _api_key:
    logger.error("OPENAI_API_KEY environment variable is not set!")

client = AsyncOpenAI(api_key=_api_key)

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
        "system": "Siz o'zbek tilida ilmiy tezis yozuvchi mutaxassississiz. Barcha matnlar to'liq o'zbek tilida bo'lishi kerak.",
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
        "system": "Siz o'zbek tilida taqdimot mazmunini yozuvchi mutaxassississiz. Barcha matnlar o'zbek tilida bo'lishi kerak.",
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


class QuotaExceededError(Exception):
    """OpenAI account has run out of credits."""

class InvalidAPIKeyError(Exception):
    """OpenAI API key is missing or invalid."""

class RateLimitedError(Exception):
    """OpenAI rate limit hit (too many requests)."""

class AIConnectionError(Exception):
    """Network error reaching OpenAI."""


async def generate_content(doc_type: str, topic: str, count: int) -> str:
    if not _api_key:
        raise InvalidAPIKeyError("OPENAI_API_KEY is not set")

    prompt_cfg = PROMPTS[doc_type]
    system_msg = prompt_cfg["system"]
    user_msg = prompt_cfg["user"](topic, count)

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=4000,
            temperature=0.7,
        )
        return response.choices[0].message.content

    except AuthenticationError as e:
        logger.error(f"OpenAI auth error: {e}")
        raise InvalidAPIKeyError(str(e)) from e

    except RateLimitError as e:
        # 429 can mean either rate-limited or quota exceeded
        msg = str(e).lower()
        logger.error(f"OpenAI rate/quota error: {e}")
        if "insufficient_quota" in msg or "exceeded your current quota" in msg:
            raise QuotaExceededError(str(e)) from e
        raise RateLimitedError(str(e)) from e

    except APIConnectionError as e:
        logger.error(f"OpenAI connection error: {e}")
        raise AIConnectionError(str(e)) from e

    except APIStatusError as e:
        logger.error(f"OpenAI API error {e.status_code}: {e}")
        if e.status_code == 429:
            raise QuotaExceededError(str(e)) from e
        raise
