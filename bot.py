# -*- coding: utf-8 -*-
import os
import sqlite3

import telebot
from telebot import types
import requests

# ============================
#   ENV SOZLAMALAR
# ============================

BOT_TOKEN = os.getenv("BOT_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# Bot username: t.me/USERNAME dagi USERNAME (@sizisiz)
# Default: Talabalar_xizmatbot
BOT_USERNAME = os.getenv("BOT_USERNAME", "Talabalar_xizmatbot")

# Admin ID – o'zingning Telegram ID (butun son)
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

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

bot = telebot.TeleBot(BOT_TOKEN)

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
    free_uses INTEGER DEFAULT 1,          -- yangi foydalanuvchi uchun 1 marta bepul
    paid_uses INTEGER DEFAULT 0,          -- to'lov orqali olingan foydalanishlar
    referral_uses INTEGER DEFAULT 0,      -- referal orqali olingan bepul foydalanishlar
    referrals_count INTEGER DEFAULT 0,    -- nechta odamni taklif qilgan
    referral_code TEXT,
    referred_by INTEGER                   -- kim orqali kelgani (telegram_id)
)
"""
)
conn.commit()

# Foydalanuvchi holati (slayd dizayn va h.k.)
user_states = {}  # {telegram_id: {...}}


# ============================
#   YORDAMCHI FUNKSIYALAR
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
        # Yangi foydalanuvchi
        referral_code = generate_referral_code(tg_id)
        cursor.execute(
            """
            INSERT INTO users (telegram_id, username, full_name, referral_code)
            VALUES (?, ?, ?, ?)
        """,
            (tg_id, username, full_name.strip(), referral_code),
        )
        conn.commit()

        # Agar referal kod orqali kelgan bo'lsa
        if ref_code_from_start:
            inviter = get_user_by_ref_code(ref_code_from_start)
            if inviter:
                inviter_tg_id = inviter[1]  # 1-ustun: telegram_id
                if inviter_tg_id != tg_id:  # o'zini o'zi taklif qilmasin
                    cursor.execute(
                        """
                        UPDATE users SET referred_by = ? WHERE telegram_id = ?
                    """,
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
                    cursor.execute(
                        """
                        SELECT referrals_count, referral_uses
                        FROM users WHERE telegram_id = ?
                    """,
                        (inviter_tg_id,),
                    )
                    r_count, r_uses = cursor.fetchone()
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

        conn.commit()
        user = get_user_by_tg_id(tg_id)
    else:
        cursor.execute(
            """
            UPDATE users SET username = ?, full_name = ? WHERE telegram_id = ?
        """,
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
            """
            UPDATE users SET free_uses = free_uses - 1 WHERE telegram_id = ?
        """,
            (telegram_id,),
        )
        conn.commit()
        return True, "free"

    if ref_uses > 0:
        cursor.execute(
            """
            UPDATE users SET referral_uses = referral_uses - 1 WHERE telegram_id = ?
        """,
            (telegram_id,),
        )
        conn.commit()
        return True, "referral"

    if paid_uses > 0:
        cursor.execute(
            """
            UPDATE users SET paid_uses = paid_uses - 1 WHERE telegram_id = ?
        """,
            (telegram_id,),
        )
        conn.commit()
        return True, "paid"

    return False, None


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
            """
            UPDATE users SET referral_code = ? WHERE telegram_id = ?
        """,
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


def ask_deepseek(prompt: str) -> str:
    """
    DeepSeek chat API orqali javob olish.
    Xatolik bo'lsa, Railway loglariga status va matnni chiqaradi.
    """
    if not DEEPSEEK_API_KEY:
        return (
            "❗️ AI kaliti topilmadi. Iltimos, admin bilan bog‘laning "
            "yoki DEEPSEEK_API_KEY env o'zgaruvchisini to'g'ri kiriting."
        )

    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    data = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Sen talabalarga slayd, mustaqil ish, referat, kurs ishi, test va boshqa "
                    "ilmiy ishlar bo‘yicha matn tayyorlab beradigan TA’LIMIY yordamchi botsan. "
                    "Matnlar O‘zbekiston ta’lim standartlariga mos, plagiatsiz va ilmiy-uslubda bo‘lsin."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }

    try:
        resp = requests.post(url, headers=headers, json=data, timeout=60)

        if resp.status_code != 200:
            # Logga yozamiz
            print("DeepSeek HTTP xato:", resp.status_code, resp.text)

            if resp.status_code in (401, 403):
                return "❗️ DeepSeek API kaliti noto‘g‘ri yoki ruxsat berilmagan. Admin kalitni tekshirishi kerak."
            if resp.status_code in (402, 429):
                return "❗️ DeepSeek API limiti yoki balans tugagan. Admin uni to‘ldirishi kerak."
            if resp.status_code == 404:
                return "❗️ DeepSeek API manzili topilmadi (URL yoki model noto‘g‘ri bo‘lishi mumkin)."
            if 500 <= resp.status_code < 600:
                return "❗️ DeepSeek serverida texnik nosozlik. Birozdan keyin yana urinib ko‘ring."

            return "❗️ DeepSeek API tomondan xatolik yuz berdi. Keyinroq yana urinib ko‘ring."

        res_json = resp.json()
        return res_json["choices"][0]["message"]["content"]

    except requests.exceptions.Timeout:
        print("DeepSeek timeout xatosi")
        return "❗️ DeepSeek serveri vaqtida javob bermadi. Keyinroq yana urinib ko‘ring."

    except Exception as e:
        print("DeepSeek umumiy xato:", e)
        return "❗️ AI xizmatida kutilmagan xatolik yuz berdi. Birozdan so‘ng qayta urinib ko‘ring."


def main_menu_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📝 Slayd", "📚 Kurs ishi")
    kb.row("👨‍🏫 Profi jamoa", "🎁 Referal bonus")
    kb.row("💵 To‘lov / Hisob", "💰 Balans", "❓ Yordam")
    return kb


# ============================
#   /START BUYRUG'I
# ============================

@bot.message_handler(commands=["start"])
def cmd_start(message: telebot.types.Message):
    parts = message.text.split()
    ref_code = parts[1] if len(parts) > 1 else None

    ensure_user(message.from_user, ref_code_from_start=ref_code)

    welcome_text = (
        "👋 *Assalomu alaykum, Talabalar Xizmati botiga xush kelibsiz!* \n\n"
        "Bu bot orqali siz ta’lim topshiriqlaringizni AI yordamida tez va sifatli "
        "tayyorlashingiz mumkin:\n\n"
        "▫️ Slayd (PPT) matni\n"
        "▫️ Mustaqil ish va referat\n"
        "▫️ Kurs ishi uchun ilmiy matnlar\n"
        "▫️ Testlar, esse va boshqa topshiriqlar\n\n"
        "🆓 *Yangi foydalanuvchi* sifatida sizga *1 marta BEPUL* foydalanish beriladi.\n"
        f"Keyingi har bir xizmat (20 listgacha slayd / mustaqil ish / referat) narxi: "
        f"*{PRICE_PER_USE} so'm*.\n\n"
        "Quyidagi menyudan kerakli bo‘limni tanlang 👇"
    )

    if LOGO_FILE_ID:
        bot.send_photo(
            message.chat.id,
            LOGO_FILE_ID,
            caption=welcome_text,
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
    else:
        bot.send_message(
            message.chat.id,
            welcome_text,
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )


# ============================
#   BALANS / REFERAL / YORDAM / TO'LOV
# ============================

@bot.message_handler(commands=["balans"])
def cmd_balance(message: telebot.types.Message):
    ensure_user(message.from_user)
    text = get_balance_text(message.from_user.id)
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(commands=["referral"])
def cmd_referral(message: telebot.types.Message):
    ensure_user(message.from_user)
    text = get_referral_info_text(message.from_user.id)
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(commands=["help"])
def cmd_help(message: telebot.types.Message):
    help_text = (
        "❓ *Yordam bo‘limi*\n\n"
        "Bot imkoniyatlari:\n"
        "1️⃣ *Slayd* – mavzu, dizayn va list soni bo‘yicha slaydlar uchun matn.\n"
        "2️⃣ *Kurs ishi* – kurs ishi rejasi va bo‘limlari bo‘yicha ilmiy matn.\n"
        "3️⃣ *Profi jamoa* – katta ishlar (kurs ishi, malakaviy ish, diplom)ni to‘liq tayyorlatish.\n"
        "4️⃣ *Referal bonus* – do‘st taklif qilib, bepul foydalanish olish.\n"
        "5️⃣ *Balans* – sizda nechta foydalanish imkoniyati borligini ko‘rish.\n"
        "6️⃣ *To‘lov / Hisob* – karta ma’lumotlari va avtomatik hisob-kitob.\n\n"
        "To‘lov cheki *asosan screenshot (rasm)* ko‘rinishida yuboriladi.\n"
        "Savollar bo‘lsa admin bilan bog‘laning: @Shokhruz11"
    )
    bot.send_message(
        message.chat.id, help_text, parse_mode="Markdown", reply_markup=main_menu_keyboard()
    )


# ============================
#   /CHEK – SCREENSHOT / MATN QABUL QILISH
# ============================

@bot.message_handler(commands=["chek"])
def cmd_chek(message: telebot.types.Message):
    bot.send_message(
        message.chat.id,
        "🧾 *To'lov cheki*\n\n"
        "Iltimos, to‘lov chekini *screenshot (rasm)* ko‘rinishida yuboring.\n"
        "Agar xohlasangiz, qo‘shimcha ravishda matn ham yozishingiz mumkin.\n\n"
        "Chekingiz admin (@Shokhruz11) tomonidan tasdiqlangach, balansingizga "
        "foydalanish huquqi qo‘shiladi.",
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(message, process_chek_message)


def process_chek_message(message: telebot.types.Message):
    tg_id = message.from_user.id
    username = (
        "@" + message.from_user.username
        if message.from_user.username
        else str(tg_id)
    )

    header = (
        "🧾 *Yangi to'lov cheki!*\n\n"
        f"Foydalanuvchi: {username}\n"
        f"Telegram ID: `{tg_id}`\n"
    )

    try:
        if ADMIN_ID:
            if message.content_type == "photo":
                photo = message.photo[-1]
                caption = header + "Chek *screenshot rasm* ko‘rinishida yuborildi."
                bot.send_photo(
                    ADMIN_ID,
                    photo.file_id,
                    caption=caption,
                    parse_mode="Markdown",
                )
            else:
                text = message.text or "(matn bo'sh)"
                caption = header + "Matn ko‘rinishidagi xabar:\n" + text
                bot.send_message(ADMIN_ID, caption, parse_mode="Markdown")

        bot.send_message(
            message.chat.id,
            "✅ Rahmat! Chekingiz admin ga yuborildi.\n"
            "Tasdiqlangach, balansingiz yangilanadi.",
        )
    except Exception:
        bot.send_message(
            message.chat.id,
            "❗️ Chek ma'lumotini admin ga yuborishda xatolik yuz berdi. "
            "Keyinroq qayta urinib ko‘ring.",
        )


# ============================
#   ADMIN BUYRUQLARI
# ============================

@bot.message_handler(commands=["add_uses"])
def cmd_add_uses(message: telebot.types.Message):
    """
    /add_uses telegram_id count
    Faqat ADMIN_ID foydalanishi mumkin.
    """
    if ADMIN_ID == 0 or message.from_user.id != ADMIN_ID:
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
        """
        SELECT paid_uses FROM users WHERE telegram_id = ?
    """,
        (target_id,),
    )
    row = cursor.fetchone()
    if row is None:
        bot.send_message(message.chat.id, "Bunday foydalanuvchi topilmadi.")
        return

    cursor.execute(
        """
        UPDATE users SET paid_uses = paid_uses + ? WHERE telegram_id = ?
    """,
        (count, target_id),
    )
    conn.commit()

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
#   MENYU HANDLERLAR
# ============================

@bot.message_handler(func=lambda m: m.text == "💰 Balans")
def handle_balance_button(message: telebot.types.Message):
    ensure_user(message.from_user)
    text = get_balance_text(message.from_user.id)
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "🎁 Referal bonus")
def handle_referral_button(message: telebot.types.Message):
    ensure_user(message.from_user)
    text = get_referral_info_text(message.from_user.id)
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "❓ Yordam")
def handle_help_button(message: telebot.types.Message):
    cmd_help(message)


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

    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=kb)


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
    bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "👨‍🏫 Profi jamoa")
def handle_prof_team(message: telebot.types.Message):
    text = (
        "👨‍🏫 *Professional jamoa – kurs ishi va diplom ishlari*\n\n"
        "Kurs ishi, malakaviy ish, diplom ishi, dissertatsiya va boshqa "
        "katta ilmiy ishlarni *to‘liq tayyorlatish* bo‘yicha professional "
        "yordam kerak bo‘lsa, to‘g‘ridan-to‘g‘ri admin bilan bog‘laning:\n\n"
        "📞 Telegram: @Shokhruz11\n\n"
        "Barcha shartlar, muddat va narxlar *faqat admin bilan kelishilgan holda* belgilanadi."
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "📚 Kurs ishi")
def handle_kurs_ishi(message: telebot.types.Message):
    ensure_user(message.from_user)
    bot.send_message(
        message.chat.id,
        "📚 Kurs ishingiz *to‘liq mavzusi*ni va agar bo‘lsa, talablari / kafedra "
        "ko‘rsatmalarini yozib yuboring.\n\n"
        "Agar kurs ishini to‘liq tayyorlatmoqchi bo‘lsangiz, "
        "👨‍🏫 *Profi jamoa* bo‘limi orqali @Shokhruz11 bilan bog‘lanishingiz mumkin.",
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(message, process_kurs_ishi_topic)


def process_kurs_ishi_topic(message: telebot.types.Message):
    topic = message.text
    tg_id = message.from_user.id
    ensure_user(message.from_user)

    ok, src = consume_credit(tg_id)
    if not ok:
        bot.send_message(
            message.chat.id,
            "❗️ Sizda bepul yoki to‘langan foydalanishlar qolmadi.\n"
            "Iltimos, *To‘lov / Hisob* bo‘limi orqali balansni to‘ldiring "
            "yoki *Referal bonus* bo‘limi orqali bepul foydalanish oling.",
            parse_mode="Markdown",
        )
        return

    bot.send_message(
        message.chat.id,
        "⏳ Kurs ishi bo‘yicha ilmiy material tayyorlanmoqda, birozdan keyin natija chiqadi...",
    )

    prompt = (
        "Quyidagi mavzu bo'yicha kurs ishi uchun ILMIY USLUBDA reja va asosiy qism "
        "bo'yicha batafsil matn tuzib ber. Matn oliy ta’lim talabi darajasida bo‘lsin.\n\n"
        f"Mavzu: {topic}\n\n"
        "Struktura: kirish, 2–3 bobli asosiy qism va xulosa.\n"
        "Har bir bob ichida kichik bo‘limlar, ilmiy tahlil va amaliy misollar bo‘lsin.\n"
        "Plagiatsiz, o‘zbek tilining ilmiy-uslubiga mos yoz."
    )
    answer = ask_deepseek(prompt)
    bot.send_message(message.chat.id, answer)


# ============================
#   SLAYD MENYUSI (6 DIZAYN)
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
        "Yangi foydalanuvchi uchun *1 marta bepul*, keyingi har bir slayd (20 listgacha) "
        f"narxi: *{PRICE_PER_USE} so'm*.\n\n"
        "Quyidagi dizaynlardan birini tanlang 👇",
        parse_mode="Markdown",
        reply_markup=kb,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("slayd_design_"))
def callback_slayd_design(call: telebot.types.CallbackQuery):
    design = call.data.split("_")[-1]  # '1'...'6'
    tg_id = call.from_user.id

    user_states[tg_id] = {
        "mode": "slayd",
        "design": design,
    }

    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        f"✅ *Dizayn {design}* tanlandi.\n"
        f"Endi necha listli slayd kerak? (1–{MAX_LIST_SLAYD} oralig‘ida son kiriting):",
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(call.message, process_slayd_lists)


def process_slayd_lists(message: telebot.types.Message):
    tg_id = message.from_user.id
    state = user_states.get(tg_id)

    if not state or state.get("mode") != "slayd":
        bot.send_message(message.chat.id, "Avval 📝 Slayd menyusidan dizayn tanlang.")
        return

    try:
        lists = int(message.text.strip())
    except ValueError:
        bot.send_message(
            message.chat.id,
            "❗️ Iltimos, faqat son kiriting. Masalan: 10",
        )
        bot.register_next_step_handler(message, process_slayd_lists)
        return

    if lists < 1 or lists > MAX_LIST_SLAYD:
        bot.send_message(
            message.chat.id,
            f"❗️ Listlar soni 1 dan {MAX_LIST_SLAYD} gacha bo'lishi kerak.",
        )
        bot.register_next_step_handler(message, process_slayd_lists)
        return

    state["lists"] = lists
    user_states[tg_id] = state

    bot.send_message(
        message.chat.id,
        "✍️ Endi slayd *mavzusini* batafsil yozib yuboring:",
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(message, process_slayd_topic)


def process_slayd_topic(message: telebot.types.Message):
    tg_id = message.from_user.id
    state = user_states.get(tg_id)

    if not state or state.get("mode") != "slayd" or "lists" not in state:
        bot.send_message(
            message.chat.id,
            "Avval 📝 Slayd menyusidan dizayn va list sonini tanlang.",
        )
        return

    topic = message.text
    design = state["design"]
    lists = state["lists"]

    ensure_user(message.from_user)

    ok, src = consume_credit(tg_id)
    if not ok:
        bot.send_message(
            message.chat.id,
            "❗️ Sizda bepul yoki to‘langan foydalanishlar qolmadi.\n"
            "Iltimos, *To‘lov / Hisob* bo‘limi orqali balansni to‘ldiring "
            "yoki *Referal bonus* bo‘limi orqali bepul foydalanish oling.",
            parse_mode="Markdown",
        )
        return

    bot.send_message(
        message.chat.id,
        "⏳ Slayd uchun matn tayyorlanmoqda, birozdan keyin natija chiqadi...",
    )

    prompt = (
        "Quyidagi parametrlar bo'yicha PREZENTATSIYA (slayd) uchun matn tuzib ber:\n\n"
        f"- Mavzu: {topic}\n"
        f"- Slaydlar (list) soni: {lists}\n"
        f"- Dizayn turi: {design}\n\n"
        "Har bir slayd uchun:\n"
        "▫️ qisqa, aniq sarlavha,\n"
        "▫️ 3–6 ta asosiy punkt,\n"
        "▫️ kerak bo‘lsa, misollar va izohlar bo‘lsin.\n\n"
        "Har slaydni 'SLAYD 1', 'SLAYD 2' ko'rinishida ajratib yoz.\n"
        "Matn o'zbek tilida, talaba uchun tushunarli va ilmiy-uslubga yaqin bo'lsin.\n"
        "Faqat slayd matnini yoz, boshqa izohlar kerak emas."
    )

    answer = ask_deepseek(prompt)
    bot.send_message(message.chat.id, answer)

    user_states.pop(tg_id, None)


# ============================
#   DEFAULT HANDLER
# ============================

@bot.message_handler(content_types=["text"])
def default_handler(message: telebot.types.Message):
    if message.text.startswith("/"):
        bot.send_message(
            message.chat.id,
            "Bu buyruq tushunarsiz. Asosiy menyudan foydalaning 👇",
            reply_markup=main_menu_keyboard(),
        )
    else:
        bot.send_message(
            message.chat.id,
            "Kerakli bo'limni menyudan tanlang 👇",
            reply_markup=main_menu_keyboard(),
        )


# ============================
#   BOTNI ISHGA TUSHIRISH
# ============================

if __name__ == "__main__":
    print("Bot ishga tushdi...")
    bot.infinity_polling(skip_pending=True)
