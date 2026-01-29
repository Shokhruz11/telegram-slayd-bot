# -*- coding: utf-8 -*-
"""
Talabalar uchun AI yordamchi Telegram bot
- OpenAI GPT-4.1-mini (GPT-4o-mini) bilan ishlaydi
- Slayd (PPTX), Mustaqil ish / referat (DOCX) fayllarini generatsiya qiladi
- Til tanlash: uz / ru / en
- 1 marta bepul, keyin pullik (balans, referal, to'lov cheki va h.k.)
"""

import os
import sqlite3

import telebot
from telebot import types
from openai import OpenAI

from pptx import Presentation
from pptx.util import Pt
from docx import Document

# ============================
#   ENV SOZLAMALAR
# ============================

BOT_TOKEN = os.getenv("8552375519:AAFIBEd_cQgGAkALULJRriYdpUFob6KQz78")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Bot username: t.me/USERNAME dagi USERNAME (@sizisiz)
BOT_USERNAME = os.getenv("BOT_USERNAME", "Talabalar_xizmatbot")

# Admin ID – sening Telegram ID'ing
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "5754599655"))
except ValueError:
    ADMIN_ID = 0

# To'lov ma'lumotlari
CARD_NUMBER = os.getenv("CARD_NUMBER", "4790 9200 1858 5070")
CARD_OWNER = os.getenv("CARD_OWNER", "Qo'chqorov Shohruz")

# 20 listgacha slayd / mustaqil ish / referat narxi
PRICE_PER_USE = int(os.getenv("PRICE_PER_USE", "5000"))  # so'm
MAX_LIST_SLAYD = int(os.getenv("MAX_LIST_SLAYD", "20"))

# Start menyu logotipi uchun Telegram file_id (bo'lsa)
LOGO_FILE_ID = os.getenv("LOGO_FILE_ID", "")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env o'zgaruvchisi topilmadi")

if not OPENAI_API_KEY:
    print("⚠️ OGОHLANTIRISH: OPENAI_API_KEY o'rnatilmagan. AI funksiyalari ishlamaydi.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# OpenAI client (kalit bo'lmasa None bo'ladi)
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# ============================
#   MA'LUMOTLAR BAZASI
# ============================

conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute(
    """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE,
    username TEXT,
    full_name TEXT,
    free_uses INTEGER DEFAULT 1,
    paid_uses INTEGER DEFAULT 0,
    referral_uses INTEGER DEFAULT 0,
    referrals_count INTEGER DEFAULT 0,
    referral_code TEXT,
    referred_by INTEGER,
    language TEXT
)
"""
)
conn.commit()

# Foydalanuvchi holati (slayd dizayn, chek, h.k.)
# misol: { tg_id: {"mode": "slayd_step_topic", "design": "1", "lists": 10} }
user_states = {}

# ============================
#   LANGUAGE FUNKSIYALARI
# ============================

def get_user_language(tg_id: int) -> str:
    cursor.execute("SELECT language FROM users WHERE telegram_id = ?", (tg_id,))
    row = cursor.fetchone()
    if row is None or not row[0]:
        return "uz"
    return row[0]


def set_user_language(tg_id: int, lang: str):
    cursor.execute(
        "UPDATE users SET language = ? WHERE telegram_id = ?",
        (lang, tg_id),
    )
    conn.commit()


def language_label(lang: str) -> str:
    if lang == "ru":
        return "Русский"
    if lang == "en":
        return "English"
    return "O‘zbekcha"


# ============================
#   USER / BALANS / REFERRAL
# ============================

def generate_referral_code(telegram_id: int) -> str:
    return f"REF{telegram_id}"


def get_user_by_tg_id(tg_id: int):
    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (tg_id,))
    return cursor.fetchone()


def get_user_by_ref_code(code: str):
    cursor.execute("SELECT * FROM users WHERE referral_code = ?", (code,))
    return cursor.fetchone()


def ensure_user(tg_user, ref_code_from_start=None):
    """
    Foydalanuvchini bazadan topadi, bo'lmasa yaratadi.
    Agar /start orqali referal kod bilan kirgan bo'lsa, uni qayd etadi.
    """
    tg_id = tg_user.id
    username = tg_user.username or ""
    full_name = (tg_user.first_name or "") + " " + (tg_user.last_name or "")

    user = get_user_by_tg_id(tg_id)
    if user is None:
        referral_code = generate_referral_code(tg_id)
        cursor.execute(
            """
            INSERT INTO users (telegram_id, username, full_name, referral_code, language)
            VALUES (?, ?, ?, ?, ?)
        """,
            (tg_id, username, full_name.strip(), referral_code, "uz"),
        )
        conn.commit()

        # Agar referal kod orqali kelgan bo'lsa
        if ref_code_from_start:
            inviter = get_user_by_ref_code(ref_code_from_start)
            if inviter:
                inviter_tg_id = inviter[1]  # telegram_id
                if inviter_tg_id != tg_id:  # o'zini o'zi taklif qilmasin
                    cursor.execute(
                        "UPDATE users SET referred_by = ? WHERE telegram_id = ?",
                        (inviter_tg_id, tg_id),
                    )
                    cursor.execute(
                        """
                        UPDATE users
                        SET referrals_count = referrals_count + 1
                        WHERE telegram_id = ?
                    """,
                        (inviter_tg_id,),
                    )
                    conn.commit()

                    cursor.execute(
                        """
                        SELECT referrals_count
                        FROM users WHERE telegram_id = ?
                    """,
                        (inviter_tg_id,),
                    )
                    r_count = cursor.fetchone()[0]

                    # Har 2 ta referal uchun 1 marta bepul foydalanish
                    if r_count % 2 == 0:
                        cursor.execute(
                            """
                            UPDATE users
                            SET referral_uses = referral_uses + 1
                            WHERE telegram_id = ?
                        """,
                            (inviter_tg_id,),
                        )
                        conn.commit()
                        try:
                            bot.send_message(
                                inviter_tg_id,
                                "🎉 Tabriklaymiz! Siz 2 ta do'stni taklif qildingiz.\n"
                                "Sizga 1 marta bepul foydalanish qo‘shildi! 🎁",
                            )
                        except Exception:
                            pass

        user = get_user_by_tg_id(tg_id)
    else:
        cursor.execute(
            "UPDATE users SET username = ?, full_name = ? WHERE telegram_id = ?",
            (username, full_name.strip(), tg_id),
        )
        conn.commit()
        user = get_user_by_tg_id(tg_id)
    return user


def consume_credit(telegram_id: int):
    """
    Foydalanuvchidan bitta 'foydalanish huquqi' (kredit) yechadi.
    Tartib:
        1) free_uses
        2) referral_uses
        3) paid_uses
    Natija:
        (True/False, "free"/"referral"/"paid"/None)
    """
    cursor.execute(
        """
        SELECT free_uses, referral_uses, paid_uses
        FROM users WHERE telegram_id = ?
    """,
        (telegram_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return False, None

    free_uses, ref_uses, paid_uses = row

    if free_uses > 0:
        cursor.execute(
            "UPDATE users SET free_uses = free_uses - 1 WHERE telegram_id = ?",
            (telegram_id,),
        )
        conn.commit()
        return True, "free"

    if ref_uses > 0:
        cursor.execute(
            "UPDATE users SET referral_uses = referral_uses - 1 WHERE telegram_id = ?",
            (telegram_id,),
        )
        conn.commit()
        return True, "referral"

    if paid_uses > 0:
        cursor.execute(
            "UPDATE users SET paid_uses = paid_uses - 1 WHERE telegram_id = ?",
            (telegram_id,),
        )
        conn.commit()
        return True, "paid"

    return False, None


def add_paid_uses(telegram_id: int, count: int):
    cursor.execute(
        "UPDATE users SET paid_uses = paid_uses + ? WHERE telegram_id = ?",
        (count, telegram_id),
    )
    conn.commit()


def get_balance_text(telegram_id: int) -> str:
    cursor.execute(
        """
        SELECT free_uses, referral_uses, paid_uses, referrals_count
        FROM users WHERE telegram_id = ?
    """,
        (telegram_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return "Foydalanuvchi topilmadi."

    free_uses, ref_uses, paid_uses, ref_count = row
    total = free_uses + ref_uses + paid_uses
    text = (
        "💰 *Balans ma'lumotlari:*\n\n"
        f"▫️ Birinchi bepul foydalanish: {free_uses} ta\n"
        f"▫️ Referal orqali olingan bepul foydalanishlar: {ref_uses} ta\n"
        f"▫️ To'langan foydalanishlar: {paid_uses} ta\n"
        f"▫️ Jami foydalanish imkoniyati: {total} ta\n\n"
        f"👥 Siz taklif qilgan do'stlar soni: {ref_count} ta\n"
        f"💸 20 listgacha slayd / mustaqil ish / referat narxi: {PRICE_PER_USE} so'm\n"
    )
    return text


def get_referral_info_text(tg_id: int) -> str:
    cursor.execute(
        """
        SELECT referral_code, referrals_count, referral_uses
        FROM users WHERE telegram_id = ?
    """,
        (tg_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return "Foydalanuvchi topilmadi."

    code, r_count, r_uses = row
    if not code:
        code = generate_referral_code(tg_id)
        cursor.execute(
            "UPDATE users SET referral_code = ? WHERE telegram_id = ?",
            (code, tg_id),
        )
        conn.commit()

    link = f"https://t.me/{BOT_USERNAME}?start={code}"
    handle = f"@{BOT_USERNAME}"
    text = (
        "📎 *Referal tizimi – do'st taklif qilib bonus oling!*\n\n"
        f"Bot nomi: {handle}\n\n"
        "Ushbu havolani do'stlaringizga yuboring. Har *2 ta* do'stingiz "
        "sizning havolangiz orqali botga /start bossa, sizga *1 marta bepul* "
        "foydalanish qo'shiladi.\n\n"
        f"🔗 Sizning referal havolangiz:\n`{link}`\n\n"
        f"👥 Hozirga qadar taklif qilgan do'stlaringiz: {r_count} ta\n"
        f"🎁 Referal orqali olingan bepul foydalanishlar: {r_uses} ta\n"
    )
    return text


# ============================
#   AI FUNKSIYASI (OpenAI)
# ============================

def ask_gpt(prompt: str, lang: str) -> str:
    """
    OpenAI GPT-4.1-mini orqali javob olish.
    Javob foydalanuvchi tanlagan tilda bo'ladi: uz / ru / en
    """
    if client is None or not OPENAI_API_KEY:
        return (
            "❗️ AI kaliti (OPENAI_API_KEY) topilmadi. Iltimos, admin bilan bog‘laning."
        )

    if lang == "ru":
        lang_desc = "Russian"
    elif lang == "en":
        lang_desc = "English"
    else:
        lang_desc = "Uzbek"

    system_text = (
        "You are an AI assistant that helps students generate educational texts: "
        "slides content, coursework, independent assignments, essays, summaries and tests. "
        "Always write in a clear, academic style appropriate for university and college students. "
        f"All answers must be written in {lang_desc} language. "
        "Do not switch to other languages."
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_text},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content
    except Exception as e:
        print("OpenAI xato:", e)
        return "❗️ AI xizmatida kutilmagan xatolik yuz berdi. Birozdan so‘ng qayta urinib ko‘ring."


# ============================
#   PPTX / DOCX GENERATORLAR
# ============================

def parse_slides_from_text(text: str):
    """
    GPT qaytargan matndan slaydlar ro'yxatini ajratib oladi.
    Kutilayotgan format: "SLIDE 1", "SLIDE 2", yoki "SLAYD 1" kabi sarlavhalar.
    """
    lines = text.replace("\r", "").split("\n")
    slides = []
    current = {"title": "", "bullets": []}

    def push_current():
        if current["title"] or current["bullets"]:
            slides.append(
                {
                    "title": current["title"].strip() or "Slide",
                    "bullets": [b.strip() for b in current["bullets"] if b.strip()],
                }
            )

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        upper = stripped.upper()
        if upper.startswith("SLIDE") or upper.startswith("SLAYD"):
            push_current()
            current = {"title": "", "bullets": []}
            parts = stripped.split(":", 1)
            if len(parts) == 2:
                current["title"] = parts[1]
            else:
                current["title"] = ""
        elif stripped.startswith(("-", "•", "*")):
            current["bullets"].append(stripped.lstrip("-•* ").strip())
        else:
            if not current["title"]:
                current["title"] = stripped
            else:
                current["bullets"].append(stripped)

    push_current()

    if not slides:
        slides = [
            {
                "title": "Slayd",
                "bullets": [line for line in lines if line.strip()],
            }
        ]
    return slides


def apply_design_to_slide(slide, design: str):
    """
    Dizayn raqamiga qarab slaydga sodda stil berish.
    """
    title_shape = slide.shapes.title
    body = None
    if len(slide.placeholders) > 1:
        body = slide.placeholders[1].text_frame

    if title_shape:
        title_shape.text_frame.paragraphs[0].font.bold = True
        if design == "1":
            title_shape.text_frame.paragraphs[0].font.size = Pt(40)
        elif design == "2":
            title_shape.text_frame.paragraphs[0].font.size = Pt(34)
        elif design == "3":
            title_shape.text_frame.paragraphs[0].font.size = Pt(32)
        else:
            title_shape.text_frame.paragraphs[0].font.size = Pt(36)

    if body:
        for p in body.paragraphs:
            p.font.size = Pt(22)

    from pptx.dml.color import RGBColor

    bg = slide.background
    fill = bg.fill
    fill.solid()

    if design == "1":
        fill.fore_color.rgb = RGBColor(255, 255, 255)
    elif design == "2":
        fill.fore_color.rgb = RGBColor(230, 242, 255)
    elif design == "3":
        fill.fore_color.rgb = RGBColor(242, 242, 242)
    elif design == "4":
        fill.fore_color.rgb = RGBColor(255, 242, 204)
    elif design == "5":
        fill.fore_color.rgb = RGBColor(226, 239, 218)
    else:
        fill.fore_color.rgb = RGBColor(237, 237, 255)


def create_pptx_from_text(text: str, design: str, filename: str):
    prs = Presentation()
    slides = parse_slides_from_text(text)

    for sl in slides:
        layout = prs.slide_layouts[1]  # title + content
        slide = prs.slides.add_slide(layout)
        slide.shapes.title.text = sl["title"]

        body = slide.placeholders[1].text_frame
        body.clear()
        first = True
        for bullet in sl["bullets"]:
            if first:
                p = body.paragraphs[0]
                first = False
            else:
                p = body.add_paragraph()
            p.text = bullet
            p.level = 0

        apply_design_to_slide(slide, design)

    prs.save(filename)


def create_docx_from_text(text: str, filename: str, title: str = None):
    doc = Document()
    if title:
        doc.add_heading(title, level=1)
        doc.add_paragraph()

    for block in text.replace("\r", "").split("\n\n"):
        block = block.strip()
        if not block:
            continue
        doc.add_paragraph(block)

    doc.save(filename)


# ============================
#   MENYU
# ============================

def main_menu_keyboard(_tg_id: int = None):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📝 Slayd", "📚 Kurs ishi")
    kb.row("📄 Mustaqil ish / Referat", "👨‍🏫 Profi jamoa")
    kb.row("🎁 Referal bonus", "💰 Balans")
    kb.row("💵 To‘lov / Hisob", "🌐 Til / Language", "❓ Yordam")
    return kb


# ============================
#   /START
# ============================

@bot.message_handler(commands=["start"])
def cmd_start(message: telebot.types.Message):
    parts = message.text.split()
    ref_code = parts[1] if len(parts) > 1 else None

    ensure_user(message.from_user, ref_code_from_start=ref_code)
    lang = get_user_language(message.from_user.id)

    welcome_text = (
        "👋 *Assalomu alaykum, Talabalar Xizmati botiga xush kelibsiz!* \n\n"
        "Bu bot orqali siz ta’lim topshiriqlaringizni AI yordamida tez va sifatli "
        "tayyorlashingiz mumkin:\n\n"
        "▫️ Slayd (PPTX) matni va fayli\n"
        "▫️ Mustaqil ish va referat (DOCX)\n"
        "▫️ Kurs ishi uchun ilmiy matnlar\n"
        "▫️ Testlar, esse va boshqa topshiriqlar\n\n"
        "🆓 *Yangi foydalanuvchi* sifatida sizga *1 marta BEPUL* foydalanish beriladi.\n"
        f"Keyingi har bir xizmat (20 listgacha slayd / mustaqil ish / referat) narxi: "
        f"*{PRICE_PER_USE} so'm*.\n\n"
        f"🔤 Joriy til: *{language_label(lang)}*\n"
        "Tilni o‘zgartirish uchun: 🌐 Til / Language tugmasini bosing.\n\n"
        "Quyidagi menyudan kerakli bo‘limni tanlang 👇"
    )

    if LOGO_FILE_ID:
        bot.send_photo(
            message.chat.id,
            LOGO_FILE_ID,
            caption=welcome_text,
            reply_markup=main_menu_keyboard(message.from_user.id),
        )
    else:
        bot.send_message(
            message.chat.id,
            welcome_text,
            reply_markup=main_menu_keyboard(message.from_user.id),
        )


# ============================
#   TIL MENYUSI
# ============================

@bot.message_handler(commands=["language"])
@bot.message_handler(func=lambda m: m.text == "🌐 Til / Language")
def cmd_language(message: telebot.types.Message):
    ensure_user(message.from_user)
    current_lang = get_user_language(message.from_user.id)

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🇺🇿 O‘zbekcha", callback_data="set_lang_uz"),
        types.InlineKeyboardButton("🇷🇺 Русский", callback_data="set_lang_ru"),
        types.InlineKeyboardButton("🇬🇧 English", callback_data="set_lang_en"),
    )

    text = (
        "🌐 *Tilni tanlang / Choose language:*\n\n"
        f"Joriy til: *{language_label(current_lang)}*"
    )
    bot.send_message(message.chat.id, text, reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("set_lang_"))
def callback_set_language(call: telebot.types.CallbackQuery):
    lang_code = call.data.split("_")[-1]
    if lang_code not in ("uz", "ru", "en"):
        bot.answer_callback_query(call.id, "Xatolik!")
        return

    set_user_language(call.from_user.id, lang_code)
    bot.answer_callback_query(call.id, "Til yangilandi ✅")

    txt = "✅ Til yangilandi: *" + language_label(lang_code) + "*"
    bot.edit_message_text(
        txt,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
    )
    bot.send_message(
        call.message.chat.id,
        "Endi AI tomonidan yaratiladigan barcha matnlar shu tilda bo‘ladi.",
        reply_markup=main_menu_keyboard(call.from_user.id),
    )


# ============================
#   BALANS / REFERAL / YORDAM
# ============================

@bot.message_handler(commands=["balans"])
@bot.message_handler(func=lambda m: m.text == "💰 Balans")
def handle_balance(message: telebot.types.Message):
    ensure_user(message.from_user)
    text = get_balance_text(message.from_user.id)
    bot.send_message(message.chat.id, text)


@bot.message_handler(commands=["referral"])
@bot.message_handler(func=lambda m: m.text == "🎁 Referal bonus")
def handle_referral(message: telebot.types.Message):
    ensure_user(message.from_user)
    text = get_referral_info_text(message.from_user.id)
    bot.send_message(message.chat.id, text)


@bot.message_handler(commands=["help"])
@bot.message_handler(func=lambda m: m.text == "❓ Yordam")
def cmd_help(message: telebot.types.Message):
    help_text = (
        "❓ *Yordam bo‘limi*\n\n"
        "Bot imkoniyatlari:\n"
        "1️⃣ *Slayd* – mavzu, dizayn va list soni bo‘yicha slaydlar uchun matn va PPTX fayl.\n"
        "2️⃣ *Mustaqil ish / referat* – DOCX faylga tushirilgan matn.\n"
        "3️⃣ *Kurs ishi* – kurs ishi rejasi va bo‘limlari bo‘yicha ilmiy matn.\n"
        "4️⃣ *Profi jamoa* – katta ishlar (kurs ishi, malakaviy ish, diplom)ni to‘liq tayyorlatish.\n"
        "5️⃣ *Referal bonus* – do‘st taklif qilib, bepul foydalanish olish.\n"
        "6️⃣ *Balans* – sizda nechta foydalanish imkoniyati borligini ko‘rish.\n"
        "7️⃣ *To‘lov / Hisob* – karta ma’lumotlari va avtomatik hisob-kitob.\n"
        "8️⃣ *Til / Language* – AI matnlarini qaysi tilda yozishni tanlash.\n\n"
        "To‘lov cheki *screenshot (rasm)* ko‘rinishida yuboriladi (/chek).\n"
        "Savollar bo‘lsa admin bilan bog‘laning: @Shokhruz11"
    )
    bot.send_message(
        message.chat.id,
        help_text,
        reply_markup=main_menu_keyboard(message.from_user.id),
    )


# ============================
#   TO'LOV / HISOB
# ============================

@bot.message_handler(func=lambda m: m.text == "💵 To‘lov / Hisob")
def handle_payment_button(message: telebot.types.Message):
    text = (
        "💵 *To'lov va hisob-kitob bo‘limi*\n\n"
        f"Har bir xizmat narxi: *{PRICE_PER_USE} so'm*\n"
        f"(20 listgacha *slayd / mustaqil ish / referat* uchun).\n\n"
        "To‘lovni quyidagi kartaga amalga oshiring:\n"
        f"▫️ Karta: `{CARD_NUMBER}`\n"
        f"▫️ Egasi: *{CARD_OWNER}*\n\n"
        "To‘lovdan so‘ng /chek buyrug‘i orqali chek *screenshot* yuboring.\n"
        "Admin (@Shokhruz11) tasdiqlagach, balansingizga xizmat qo‘shiladi.\n\n"
        "👇 Nechta foydalanish uchun to‘lov qilmoqchi ekanligingizni tanlasangiz, "
        "bot jami summani avtomatik hisoblab beradi."
    )

    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("1 ta foydalanish", callback_data="calc_uses_1"),
        types.InlineKeyboardButton("2 ta", callback_data="calc_uses_2"),
    )
    kb.row(
        types.InlineKeyboardButton("5 ta", callback_data="calc_uses_5"),
        types.InlineKeyboardButton("10 ta", callback_data="calc_uses_10"),
    )

    bot.send_message(message.chat.id, text, reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("calc_uses_"))
def callback_calc_uses(call: telebot.types.CallbackQuery):
    try:
        uses = int(call.data.split("_")[-1])
    except ValueError:
        bot.answer_callback_query(call.id, "Xatolik!")
        return

    total = uses * PRICE_PER_USE
    msg = (
        f"📊 *Hisob-kitob:*\n\n"
        f"▫️ Foydalanish soni: *{uses} ta*\n"
        f"▫️ Bir martalik narx: *{PRICE_PER_USE} so'm*\n"
        f"➡️ Jami to'lov: *{total} so'm*\n\n"
        "To‘lovni amalga oshirgach, /chek buyrug‘i orqali chek screenshotini yuboring."
    )

    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, msg)


# ============================
#   /CHEK – TO'LOV CHEKI
# ============================

@bot.message_handler(commands=["chek"])
def cmd_chek(message: telebot.types.Message):
    """
    Foydalanuvchi /chek yozganda holatni 'chek'ga qo'yamiz.
    Keyingi yuborilgan foto / document / matn admin'ga jo'natiladi.
    """
    ensure_user(message.from_user)
    tg_id = message.from_user.id

    user_states[tg_id] = {"mode": "chek"}

    bot.send_message(
        message.chat.id,
        "🧾 *To'lov cheki*\n\n"
        "Iltimos, to‘lov chekini *screenshot (rasm)* yoki *fayl (document)* "
        "ko‘rinishida yuboring.\n"
        "Agar xohlasangiz, qo‘shimcha ravishda matn ham yozishingiz mumkin.\n\n"
        "Chekingiz admin (@Shokhruz11) tomonidan ko‘rib chiqiladi. "
        "Tasdiqlangach, balansingizga foydalanish huquqi qo‘shiladi.",
    )


@bot.message_handler(
    func=lambda m: user_states.get(m.from_user.id, {}).get("mode") == "chek",
    content_types=["photo", "document", "text"],
)
def handle_chek_flow(message: telebot.types.Message):
    """
    Bu handler faqat 'chek' holatidagi foydalanuvchilar uchun ishlaydi.
    Rasm / fayl yoki matnni admin'ga yuboradi, admin tasdiqlash tugmasi orqali balansni to'ldiradi.
    """
    tg_id = message.from_user.id
    username = (
        "@" + message.from_user.username
        if message.from_user.username
        else str(tg_id)
    )

    print(f"[CHEK] Keldi: user={tg_id}, turi={message.content_type}")

    header = (
        "🧾 *Yangi to'lov cheki!*\n\n"
        f"Foydalanuvchi: {username}\n"
        f"Telegram ID: `{tg_id}`\n\n"
        "Tasdiqlash uchun quyidagi tugmalardan birini bosing 👇\n"
        "(balansga nechta foydalanish qo'shilishini tanlang)"
    )

    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton(
            "✅ 1 ta foydalanish", callback_data=f"approve_{tg_id}_1"
        ),
        types.InlineKeyboardButton(
            "✅ 3 ta", callback_data=f"approve_{tg_id}_3"
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            "✅ 5 ta", callback_data=f"approve_{tg_id}_5"
        ),
    )

    try:
        if not ADMIN_ID:
            raise RuntimeError("ADMIN_ID sozlanmagan")

        if message.content_type == "photo":
            photo = message.photo[-1]
            bot.send_photo(
                ADMIN_ID,
                photo.file_id,
                caption=header,
                reply_markup=kb,
            )
        elif message.content_type == "document":
            bot.send_document(
                ADMIN_ID,
                message.document.file_id,
                caption=header,
                reply_markup=kb,
            )
        elif message.content_type == "text":
            text = message.text or "(matn bo'sh)"
            caption = header + "\n\nMatn:\n" + text
            bot.send_message(
                ADMIN_ID,
                caption,
                reply_markup=kb,
            )

        bot.send_message(
            message.chat.id,
            "✅ Rahmat! Chekingiz admin ga yuborildi.\n"
            "Tasdiqlangach, balansingiz yangilanadi.",
        )
    except Exception as e:
        print("Chek forwarding xatosi:", e)
        bot.send_message(
            message.chat.id,
            "❗️ Chek ma'lumotini admin ga yuborishda xatolik yuz berdi. "
            "Keyinroq qayta urinib ko‘ring yoki admin bilan bevosita yozishib chiqing: @Shokhruz11",
        )

    user_states.pop(tg_id, None)


@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_"))
def callback_approve_payment(call: telebot.types.CallbackQuery):
    """
    Admin uchun tasdiqlash tugmalari.
    Callback data: approve_<user_id>_<uses>
    """
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Faqat admin tasdiqlashi mumkin.")
        return

    _, user_id_str, uses_str = call.data.split("_")
    try:
        target_id = int(user_id_str)
        uses = int(uses_str)
    except ValueError:
        bot.answer_callback_query(call.id, "Xatolik!")
        return

    cursor.execute(
        "SELECT telegram_id FROM users WHERE telegram_id = ?",
        (target_id,),
    )
    row = cursor.fetchone()
    if row is None:
        bot.answer_callback_query(call.id, "Foydalanuvchi topilmadi.")
        return

    add_paid_uses(target_id, uses)
    bot.answer_callback_query(call.id, f"{uses} ta foydalanish qo'shildi ✅")

    # Admin xabarini "tasdiqlandi" deb yangilaymiz
    try:
        if call.message.content_type == "text":
            new_text = call.message.text + (
                f"\n\n✅ Admin tasdiqladi: {uses} ta foydalanish qo'shildi."
            )
            bot.edit_message_text(
                new_text,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
            )
        else:
            new_caption = (call.message.caption or "") + (
                f"\n\n✅ Admin tasdiqladi: {uses} ta foydalanish qo'shildi."
            )
            bot.edit_message_caption(
                new_caption,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
            )
    except Exception as e:
        print("Approve edit xatosi:", e)

    # Foydalanuvchini xabardor qilamiz
    try:
        bot.send_message(
            target_id,
            f"💳 To‘lovingiz admin tomonidan tasdiqlandi.\n"
            f"Balansingizga *{uses} ta* foydalanish qo‘shildi.",
        )
    except Exception as e:
        print("User notify xatosi:", e)


# ============================
#   ADMIN BUYRUQLARI
# ============================

@bot.message_handler(commands=["add_uses"])
def cmd_add_uses(message: telebot.types.Message):
    """
    /add_uses telegram_id count
    Faqat ADMIN_ID foydalanishi mumkin.
    """
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split()
    if len(parts) != 3:
        bot.send_message(message.chat.id, "Format: /add_uses <telegram_id> <soni>")
        return

    try:
        target_id = int(parts[1])
        count = int(parts[2])
    except ValueError:
        bot.send_message(message.chat.id, "ID va soni butun son bo‘lishi kerak.")
        return

    cursor.execute(
        "SELECT paid_uses FROM users WHERE telegram_id = ?",
        (target_id,),
    )
    row = cursor.fetchone()
    if row is None:
        bot.send_message(message.chat.id, "Bunday foydalanuvchi topilmadi.")
        return

    add_paid_uses(target_id, count)

    bot.send_message(
        message.chat.id, f"✅ Foydalanuvchiga {count} ta foydalanish qo‘shildi."
    )
    try:
        bot.send_message(
            target_id, f"💳 Balansingizga {count} ta foydalanish qo‘shildi."
        )
    except Exception:
        pass


# ============================
#   PROFI JAMOA / KURS ISHI / MUSTAQIL ISH
# ============================

@bot.message_handler(func=lambda m: m.text == "👨‍🏫 Profi jamoa")
def handle_prof_team(message: telebot.types.Message):
    text = (
        "👨‍🏫 *Professional jamoa – kurs ishi va diplom ishlari*\n\n"
        "Kurs ishi, malakaviy ish, diplom ishi, dissertatsiya va boshqa "
        "katta ilmiy ishlarni *to‘liq tayyorlatish* bo‘yicha professional "
        "yordam kerak bo‘lsa, to‘g‘ridan-to‘gri admin bilan bog‘laning:\n\n"
        "📞 Telegram: @Shokhruz11\n\n"
        "Barcha shartlar, muddat va narxlar *faqat admin bilan kelishilgan holda* belgilanadi."
    )
    bot.send_message(message.chat.id, text)


@bot.message_handler(func=lambda m: m.text == "📚 Kurs ishi")
def handle_kurs_ishi(message: telebot.types.Message):
    ensure_user(message.from_user)
    bot.send_message(
        message.chat.id,
        "📚 Kurs ishingiz *to‘liq mavzusi*ni va agar bo‘lsa, talablari / kafedra "
        "ko‘rsatmalarini yozib yuboring.\n\n"
        "Agar kurs ishini to‘liq tayyorlatmoqchi bo‘lsangiz, "
        "👨‍🏫 *Profi jamoa* bo‘limi orqali @Shokhruz11 bilan bog‘lanishingiz mumkin.",
    )
    bot.register_next_step_handler(message, process_kurs_ishi_topic)


def process_kurs_ishi_topic(message: telebot.types.Message):
    topic = message.text
    tg_id = message.from_user.id
    ensure_user(message.from_user)

    ok, _ = consume_credit(tg_id)
    if not ok:
        bot.send_message(
            message.chat.id,
            "❗️ Sizda bepul yoki to‘langan foydalanishlar qolmadi.\n"
            "Iltimos, *To‘lov / Hisob* bo‘limi orqali balansni to‘ldiring "
            "yoki *Referal bonus* bo‘limi orqali bepul foydalanish oling.",
        )
        return

    bot.send_message(
        message.chat.id,
        "⏳ Kurs ishi bo‘yicha ilmiy material tayyorlanmoqda...",
    )

    lang = get_user_language(tg_id)

    prompt = (
        "Create a detailed course paper structure and main text for the following topic.\n\n"
        f"Topic: {topic}\n\n"
        "Requirements:\n"
        "- Include: introduction, 2–3 chapters in the main part, and conclusion.\n"
        "- Each chapter should have sub-sections, theoretical analysis and practical examples.\n"
        "- Style: academic, clear, without plagiarism, suitable for university level.\n"
        "- Do not add any extra explanations, just the course paper text."
    )
    answer = ask_gpt(prompt, lang)
    bot.send_message(message.chat.id, answer[:4000])


@bot.message_handler(func=lambda m: m.text == "📄 Mustaqil ish / Referat")
def handle_mustaqil(message: telebot.types.Message):
    ensure_user(message.from_user)
    tg_id = message.from_user.id
    user_states[tg_id] = {"mode": "mustaqil_step_pages"}

    bot.send_message(
        message.chat.id,
        f"📄 Mustaqil ish / referat uchun taxminiy *betlar sonini* kiriting (1–{MAX_LIST_SLAYD}):",
    )


@bot.message_handler(
    func=lambda m: user_states.get(m.from_user.id, {}).get("mode") == "mustaqil_step_pages"
)
def process_mustaqil_pages(message: telebot.types.Message):
    tg_id = message.from_user.id
    state = user_states.get(tg_id, {})

    try:
        pages = int(message.text.strip())
    except ValueError:
        bot.send_message(message.chat.id, "❗️ Iltimos, faqat son kiriting. Masalan: 10")
        return

    if pages < 1 or pages > MAX_LIST_SLAYD:
        bot.send_message(
            message.chat.id,
            f"❗️ Betlar soni 1 dan {MAX_LIST_SLAYD} gacha bo‘lishi kerak.",
        )
        return

    state["pages"] = pages
    state["mode"] = "mustaqil_step_topic"
    user_states[tg_id] = state

    bot.send_message(
        message.chat.id,
        "Endi mustaqil ish / referat *mavzusini batafsil* yozib yuboring:",
    )


@bot.message_handler(
    func=lambda m: user_states.get(m.from_user.id, {}).get("mode") == "mustaqil_step_topic"
)
def process_mustaqil_topic(message: telebot.types.Message):
    tg_id = message.from_user.id
    state = user_states.get(tg_id, {})
    pages = state.get("pages", 10)
    topic = message.text

    ensure_user(message.from_user)

    ok, _ = consume_credit(tg_id)
    if not ok:
        bot.send_message(
            message.chat.id,
            "❗️ Sizda bepul yoki to‘langan foydalanishlar qolmadi.\n"
            "Iltimos, *To‘lov / Hisob* bo‘limi orqali balansni to‘ldiring "
            "yoki *Referal bonus* bo‘limi orqali bepul foydalanish oling.",
        )
        user_states.pop(tg_id, None)
        return

    bot.send_message(
        message.chat.id,
        "⏳ Mustaqil ish / referat tayyorlanmoqda...",
    )

    lang = get_user_language(tg_id)

    prompt = (
        "Write an independent work / referat for the following topic.\n\n"
        f"Topic: {topic}\n"
        f"Approximate length: {pages} pages (A4).\n\n"
        "Structure:\n"
        "- Introduction\n"
        "- 2–3 main chapters with subheadings\n"
        "- Conclusion\n\n"
        "Style: academic, clear, logically structured. No plagiarism. "
        "Return only the text of the paper, without any extra commentary."
    )

    text = ask_gpt(prompt, lang)

    bot.send_message(message.chat.id, text[:4000])

    filename = f"mustaqil_{tg_id}.docx"
    try:
        create_docx_from_text(text, filename, title=topic)
        with open(filename, "rb") as f:
            bot.send_document(
                message.chat.id,
                f,
                visible_file_name=f"Mustaqil_ish_{tg_id}.docx",
                caption="📄 Mustaqil ish / referat DOCX fayli tayyor.",
            )
    except Exception as e:
        print("DOCX yaratish xatosi:", e)
        bot.send_message(
            message.chat.id,
            "❗️ DOCX fayl yaratishda xatolik yuz berdi. Matnni qo‘lda nusxa ko‘chirib Word faylga joylashtirishingiz mumkin.",
        )
    finally:
        if os.path.exists(filename):
            os.remove(filename)

    user_states.pop(tg_id, None)


# ============================
#   SLAYD (PPTX)
# ============================

@bot.message_handler(func=lambda m: m.text == "📝 Slayd")
def handle_slayd(message: telebot.types.Message):
    ensure_user(message.from_user)

    kb = types.InlineKeyboardMarkup()
    buttons = []
    for i in range(1, 7):
        btn = types.InlineKeyboardButton(f"🎨 Dizayn {i}", callback_data=f"slayd_design_{i}")
        buttons.append(btn)

    kb.add(buttons[0], buttons[1])
    kb.add(buttons[2], buttons[3])
    kb.add(buttons[4], buttons[5])

    bot.send_message(
        message.chat.id,
        "🎓 *Slayd generatori*\n\n"
        f"1️⃣ Avval dizaynni tanlang.\n"
        f"2️⃣ Keyin slaydlar sonini kiriting (1–{MAX_LIST_SLAYD}).\n"
        "3️⃣ So‘ng mavzuni yozing – AI siz uchun ta’limga mos slayd matnini tuzib beradi.\n\n"
        "Yangi foydalanuvchi uchun *1 marta bepul*, keyingi har bir xizmat "
        f"(20 listgacha) narxi: *{PRICE_PER_USE} so'm*.\n\n"
        "Quyidagi dizaynlardan birini tanlang 👇",
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("slayd_design_"))
def callback_slayd_design(call: telebot.types.CallbackQuery):
    design = call.data.split("_")[-1]  # '1'...'6'
    tg_id = call.from_user.id

    user_states[tg_id] = {
        "mode": "slayd_step_lists",
        "design": design,
    }

    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        f"✅ *Dizayn {design}* tanlandi.\n"
        f"Endi necha listli slayd kerak? (1–{MAX_LIST_SLAYD} oralig‘ida son kiriting):",
    )


@bot.message_handler(
    func=lambda m: user_states.get(m.from_user.id, {}).get("mode") == "slayd_step_lists"
)
def process_slayd_lists(message: telebot.types.Message):
    tg_id = message.from_user.id
    state = user_states.get(tg_id)

    try:
        lists = int(message.text.strip())
    except ValueError:
        bot.send_message(
            message.chat.id,
            "❗️ Iltimos, faqat son kiriting. Masalan: 10",
        )
        return

    if lists < 1 or lists > MAX_LIST_SLAYD:
        bot.send_message(
            message.chat.id,
            f"❗️ Listlar soni 1 dan {MAX_LIST_SLAYD} gacha bo'lishi kerak.",
        )
        return

    state["lists"] = lists
    state["mode"] = "slayd_step_topic"
    user_states[tg_id] = state

    bot.send_message(
        message.chat.id,
        "✍️ Endi slayd *mavzusini* batafsil yozib yuboring:",
    )


@bot.message_handler(
    func=lambda m: user_states.get(m.from_user.id, {}).get("mode") == "slayd_step_topic"
)
def process_slayd_topic(message: telebot.types.Message):
    tg_id = message.from_user.id
    state = user_states.get(tg_id)

    if not state:
        bot.send_message(
            message.chat.id,
            "Avval 📝 Slayd menyusidan dizayn va list sonini tanlang.",
        )
        return

    topic = message.text
    design = state["design"]
    lists = state["lists"]

    ensure_user(message.from_user)

    ok, _ = consume_credit(tg_id)
    if not ok:
        bot.send_message(
            message.chat.id,
            "❗️ Sizda bepul yoki to‘langan foydalanishlar qolmadi.\n"
            "Iltimos, *To‘lov / Hisob* bo‘limi orqali balansni to‘ldiring "
            "yoki *Referal bonus* bo‘limi orqali bepul foydalanish oling.",
        )
        user_states.pop(tg_id, None)
        return

    bot.send_message(
        message.chat.id,
        "⏳ Slayd uchun matn va PPTX fayl tayyorlanmoqda...",
    )

    lang = get_user_language(tg_id)

    prompt = (
        "Generate presentation slide content with the following parameters:\n\n"
        f"- Topic: {topic}\n"
        f"- Number of slides: {lists}\n"
        f"- Design style code: {design} (use it as a style hint only).\n\n"
        "For each slide, include:\n"
        "- Short clear title\n"
        "- 3–6 bullet points with key ideas\n"
        "- Examples or brief explanations if useful\n\n"
        "Separate each slide as: SLIDE 1, SLIDE 2, etc.\n"
        "Do not add any extra commentary outside the slide texts."
    )

    text = ask_gpt(prompt, lang)

    bot.send_message(message.chat.id, text[:4000])

    filename = f"slayd_{tg_id}.pptx"
    try:
        create_pptx_from_text(text, design, filename)
        with open(filename, "rb") as f:
            bot.send_document(
                message.chat.id,
                f,
                visible_file_name=f"Slayd_{tg_id}.pptx",
                caption="📊 Slayd PPTX fayli tayyor.",
            )
    except Exception as e:
        print("PPTX yaratish xatosi:", e)
        bot.send_message(
            message.chat.id,
            "❗️ PPTX fayl yaratishda xatolik yuz berdi. Matnni qo‘lda nusxa ko‘chirib "
            "PowerPoint’ga joylashtirishingiz mumkin.",
        )
    finally:
        if os.path.exists(filename):
            os.remove(filename)

    user_states.pop(tg_id, None)


# ============================
#   DEFAULT HANDLER
# ============================

@bot.message_handler(content_types=["text"])
def default_handler(message: telebot.types.Message):
    # Yuqoridagi special handlerlar ishlamasa – bu yerga tushadi
    if message.text.startswith("/"):
        bot.send_message(
            message.chat.id,
            "Bu buyruq tushunarsiz. Asosiy menyudan foydalaning 👇",
            reply_markup=main_menu_keyboard(message.from_user.id),
        )
    else:
        bot.send_message(
            message.chat.id,
            "Kerakli bo'limni menyudan tanlang 👇",
            reply_markup=main_menu_keyboard(message.from_user.id),
        )


# ============================
#   BOTNI ISHGA TUSHIRISH
# ============================

if __name__ == "__main__":
    print("Bot ishga tushdi...")
    bot.infinity_polling(skip_pending=True)

