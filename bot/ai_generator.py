import os
from openai import AsyncOpenAI

client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

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


async def generate_content(doc_type: str, topic: str, count: int) -> str:
    prompt_cfg = PROMPTS[doc_type]
    system_msg = prompt_cfg["system"]
    user_msg = prompt_cfg["user"](topic, count)

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
