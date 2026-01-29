# -*- coding: utf-8 -*-
import os
import sqlite3
from datetime import datetime

import telebot
from telebot import types
import requests

# ============================
#   ENV SOZLAMALAR
# ============================

# Bu qiymatlarni Railway/Render yoki lokal .env da berasan:
# BOT_TOKEN, DEEPSEEK_API_KEY, BOT_USERNAME, ADMIN_ID
BOT_TOKEN = os.getenv("BOT_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# Bot username: t.me/USERNAME dagi USERNAME ( @sizisiz )
BOT_USERNAME = os.getenv("BOT_USERNAME", "YourBotUserNameHere")

# Admin ID – o'zingning Telegram ID (butun son)
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# To'lov ma'lumotlari
CARD_NUMBER = os.getenv("CARD_NUMBER", "4790 9200 1858 5070")
CARD_OWNER = os.getenv("CARD_OWNER", "Qo'chqorov Shohruz")
PRICE_PER_USE = int(os.getenv("PRICE_PER_USE", "5000"))  # so'm
MAX_LIST_SLAYD = int(os.getenv("MAX_LIST_SLAYD", "20"))

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
                    # invited userga referred_by yozamiz
                    cursor.execute(
                        """
                        UPDATE users SET referred_by = ? WHERE telegram_id = ?
                    """,
                        (inviter_tg_id, tg_id),
                    )
                    # inviterning referal sonini oshiramiz
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
                                "Sizga 1 marta bepul foydalanish qo‘shildi!",
                            )
                        except Exception:
                            pass

        conn.commit()
        user = get_user_by_tg_id(tg_id)
    else:
        # Mavjud foydalanuvchining username/full_name ni yangilaymiz
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
        f"💸 Har bir qo‘shimcha foydalanish narxi: {PRICE_PER_USE} so'm\n"
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
    text = (
        "📎 *Referal tizimi:*\n\n"
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
    """
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
                    "Sen talabalarga slayd, referat, kurs ishi, test va boshqa "
                    "ilmiy-ishlar bo'yicha matn tayyorlab beradigan yordamchi botsan. "
                    "O'zbek tilida, tushunarli va aniq yoz."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        res_json = response.json()
        return res_json["choices"][0]["message"]["content"]
    except Exception as e:
        print("DeepSeek xatosi:", e)
        return "❗️ AI xizmatida kutilmagan xatolik yuz berdi. Birozdan so‘ng qayta urinib ko‘ring."


def main_menu_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📝 Slayd", "📚 Kurs ishi")
    kb.row("👨‍🏫 Professional jamoa", "📎 Referal tizimi")
    kb.row("💳 To‘lov", "💰 Balans", "ℹ️ Yordam")
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
        "Assalomu alaykum! 👋\n\n"
        "Ushbu bot orqali siz:\n"
        "▫️ Slayd (PPT) matni\n"
        "▫️ Mustaqil ish, referat\n"
        "▫️ Kurs ishi uchun materiallar\n"
        "▫️ Test, esse va boshqa topshiriqlar\n"
        "tayyorlashda AI yordamidan foydalanishingiz mumkin.\n\n"
        "🆓 Yangi foydalanuvchilarga *1 marta BEPUL* foydalanish beriladi.\n"
        f"Keyingi har bir foydalanish narxi: *{PRICE_PER_USE} so'm*.\n\n"
        "Asosiy menyudan kerakli bo‘limni tanlang 👇"
    )

    bot.send_message(message.chat.id, welcome_text, reply_markup=main_menu_keyboard())


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
        "ℹ️ *Yordam:*\n\n"
        "1️⃣ Slayd – mavzu, dizayn va list soni bo‘yicha slayd matni tuzib beradi.\n"
        "2️⃣ Kurs ishi – kurs ishi uchun reja va matn bo‘yicha yordam beradi.\n"
        "3️⃣ Professional jamoa – kurs ishi va diplom ishi bo‘yicha "
        "bevosita admin bilan bog‘lanish.\n"
        "4️⃣ Referal tizimi – 2 ta do‘stni taklif qilsangiz, 1 marta bepul.\n"
        "5️⃣ Balans – bepul va to‘langan foydalanishlar sonini ko‘rish.\n"
        "6️⃣ To‘lov – karta raqami va to‘lov tartibi.\n\n"
        "Qo‘shimcha savollar bo‘lsa admin bilan bog‘laning: @Shokhruz11"
    )
    bot.send_message(
        message.chat.id, help_text, parse_mode="Markdown", reply_markup=main_menu_keyboard()
    )


@bot.message_handler(commands=["chek"])
def cmd_chek(message: telebot.types.Message):
    """
    Foydalanuvchi to'lov chek ma'lumotini yuborishi uchun.
    Admin uchun xabarni forward qiladi.
    """
    bot.send_message(
        message.chat.id,
        "💳 To'lov chek ma'lumotini yozib yuboring.\n"
        "Masalan:\n"
        "`50 000 so'm, 8600 **** **** 1234, 29.01.2026 22:15`",
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(message, process_chek_text)


def process_chek_text(message: telebot.types.Message):
    text = message.text
    tg_id = message.from_user.id
    username = "@" + message.from_user.username if message.from_user.username else str(
        tg_id
    )

    admin_msg = (
        "🧾 *Yangi to'lov cheki!*\n\n"
        f"Foydalanuvchi: {username}\n"
        f"Telegram ID: `{tg_id}`\n"
        f"Xabar:\n{text}"
    )
    try:
        if ADMIN_ID:
            bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown")
        bot.send_message(
            message.chat.id,
            "✅ Rahmat! Chek ma'lumotingiz admin ga yuborildi.\n"
            "Tez orada balansingiz yangilanadi.",
        )
    except Exception:
        bot.send_message(
            message.chat.id,
            "❗️ Chek ma'lumotini admin ga yuborishda xatolik yuz berdi. "
            "Iltimos, keyinroq qayta urinib ko‘ring.",
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
        bot.send_message(target_id, f"💳 Balansingizga {count} ta foydalanish qo‘shildi.")
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


@bot.message_handler(func=lambda m: m.text == "📎 Referal tizimi")
def handle_referral_button(message: telebot.types.Message):
    ensure_user(message.from_user)
    text = get_referral_info_text(message.from_user.id)
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "ℹ️ Yordam")
def handle_help_button(message: telebot.types.Message):
    cmd_help(message)


@bot.message_handler(func=lambda m: m.text == "💳 To‘lov")
def handle_payment_button(message: telebot.types.Message):
    text = (
        "💳 *To'lov tartibi:*\n\n"
        f"1️⃣ Kartaga to'lov qiling:\n"
        f"▫️ Karta: `{CARD_NUMBER}`\n"
        f"▫️ Egasi: *{CARD_OWNER}*\n\n"
        f"2️⃣ Har bir foydalanish narxi: *{PRICE_PER_USE} so'm* "
        f"(20 listgacha slayd uchun).\n\n"
        "3️⃣ To'lovni amalga oshirgandan so'ng, /chek buyrug'i orqali chek ma'lumotini yuboring.\n"
        "4️⃣ Admin balansingizga foydalanish huquqlarini qo‘shib beradi.\n\n"
        "Savollar bo'lsa: @Shokhruz11"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "👨‍🏫 Professional jamoa")
def handle_prof_team(message: telebot.types.Message):
    text = (
        "👨‍🏫 *Professional jamoa:*\n\n"
        "Kurs ishi, malakaviy ish, diplom ishi, dissertatsiya va boshqa "
        "katta ilmiy ishlar bo‘yicha professional yordam uchun admin bilan "
        "bevosita bog‘laning:\n\n"
        "📞 Telegram: @Shokhruz11\n\n"
        "Kurs ishi va diplom ishlar *admin bilan kelishilgan holda* bajariladi."
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "📚 Kurs ishi")
def handle_kurs_ishi(message: telebot.types.Message):
    ensure_user(message.from_user)
    bot.send_message(
        message.chat.id, "📚 Kurs ishingiz mavzusini batafsil yozib yuboring:"
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
            "Iltimos, To‘lov bo‘limi orqali balansni to‘ldiring yoki referal "
            "tizimi orqali bepul foydalanish oling.",
        )
        return

    bot.send_message(
        message.chat.id,
        "⏳ Kurs ishi bo‘yicha material tayyorlanmoqda, biroz kuting...",
    )

    prompt = (
        "Quyidagi mavzu bo'yicha kurs ishi uchun ILMIY USLUBDA reja va asosiy qism "
        "bo'yicha batafsil matn tuzib ber:\n\n"
        f"Mavzu: {topic}\n\n"
        "Matnda: kirish, 2-3 bobli asosiy qism va xulosa bo'lsin. "
        "O'zbek tilining ilmiy-uslubiga mos yoz."
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
        btn = types.InlineKeyboardButton(f"Dizayn {i}", callback_data=f"slayd_design_{i}")
        buttons.append(btn)

    kb.add(buttons[0], buttons[1])
    kb.add(buttons[2], buttons[3])
    kb.add(buttons[4], buttons[5])

    bot.send_message(
        message.chat.id,
        "🎨 6 xil slayd dizaynidan birini tanlang:",
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
        f"✅ Dizayn {design} tanlandi.\n"
        f"Necha listli slayd kerak? (1–{MAX_LIST_SLAYD} oralig‘ida son kiriting):",
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
        "✍️ Endi slayd mavzusini batafsil yozib yuboring:",
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
            "Iltimos, To‘lov bo‘limi orqali balansni to‘ldiring yoki referal "
            "tizimi orqali bepul foydalanish oling.",
        )
        return

    bot.send_message(
        message.chat.id,
        "⏳ Slayd uchun matn tayyorlanmoqda, biroz kuting...",
    )

    prompt = (
        "Quyidagi parametrlar bo'yicha PREZENTATSIYA (slayd) uchun matn tuzib ber:\n\n"
        f"- Mavzu: {topic}\n"
        f"- Slaydlar (list) soni: {lists}\n"
        f"- Dizayn turi: {design}\n\n"
        "Har bir slayd uchun alohida sarlavha va punktlar bo'lsin.\n"
        "Har slaydni 'SLAYD 1', 'SLAYD 2' ko'rinishida ajratib yoz.\n"
        "Matn o'zbek tilida, talaba uchun tushunarli va aniq bo'lsin.\n"
        "Faqat matnni yoz, boshqa izohlar kerak emas."
    )

    answer = ask_deepseek(prompt)
    bot.send_message(message.chat.id, answer)

    user_states.pop(tg_id, None)


# ============================
#   DEFAULT HANDLER
# ============================

@bot.message_handler(content_types=["text"])
def default_handler(message: telebot.types.Message):
    """
    Agar foydalanuvchi boshqa narsa yozsa – menyuni eslatamiz.
    """
    if message.text.startswith("/"):
        bot.send_message(
            message.chat.id,
            "Bu buyruq tushunarsiz. Asosiy menyudan foydalaning.",
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
    # skip_pending=True – eski xabarlarni o'qimaydi
    bot.infinity_polling(skip_pending=True)
