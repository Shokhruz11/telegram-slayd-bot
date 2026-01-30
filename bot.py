# -*- coding: utf-8 -*-
"""
SUPER TALABA BOT
-----------------

Funksiyalar:
- Slayd (PPTX) generatsiyasi (6 xil dizayn)
- Mustaqil ish / Referat (DOCX)
- Kurs ishi (DOCX) – hozir referat logikasi bilan
- Har bir foydalanuvchiga MAX_FREE_LIMIT marta bepul (env orqali)
- Keyingi buyurtmalar 20 betgacha/pptgacha pullik
- To'lov cheki rasm sifatida, admin tasdiqlaydi
- Admin tasdiqlasa – fayl yaratiladi va foydalanuvchiga yuboriladi

Muhim:
- HTML/Markdown ishlatilmaydi (parse entities xatolarini oldini olish uchun)
- Railway environment variables bilan ishlaydi
"""

import os
import sqlite3
from datetime import datetime

import telebot
from telebot import types
import openai

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor

from docx import Document


# ============================
#      ENV SOZLAMALAR
# ============================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID", "")
try:
    ADMIN_TELEGRAM_ID = int(ADMIN_TELEGRAM_ID)
except Exception:
    ADMIN_TELEGRAM_ID = 0  # agar noto'g'ri bo'lsa, callbackda tekshiramiz

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "@admin")

CARD_NUMBER = os.getenv("CARD_NUMBER", "0000 0000 0000 0000")
CARD_OWNER = os.getenv("CARD_OWNER", "Karta egasi")

# Nechta bepul buyurtma
try:
    MAX_FREE_LIMIT = int(os.getenv("MAX_FREE_LIMIT", "1"))
except Exception:
    MAX_FREE_LIMIT = 1

# Narx (so'm) – hozircha bitta tarif
PRICE_PER_ORDER = 5000
MAX_PAGES_PER_ORDER = 20

DB_NAME = "bot_db.sqlite3"
FILES_DIR = "generated_files"

# # OpenAI klient
client = OpenAI(api_key=OPENAI_API_KEY)

client = OpenAI(api_key=OPENAI_API_KEY)

# TeleBot (parse_mode bermaymiz, oddiy matn)
bot = telebot.TeleBot(BOT_TOKEN)

# User holatlari
user_states = {}   # chat_id -> state
user_context = {}  # chat_id -> dict


# ============================
#      YORDAMCHI FUNKSIYALAR
# ============================

def ask_gpt(prompt: str, max_tokens: int = 2048) -> str:
    """GPT-4o-mini bilan matn generatsiyasi."""
    try:
        completion = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Sen talabalarga ilmiy-uslubda yordam beradigan yordamchi bo'lasan."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
        )
        # eski API uslubi: message["content"]
        return completion.choices[0].message["content"]
    except Exception as e:
        print("OpenAI xatosi:", e)
        return f"ERROR: {e}"

    # Buyurtmalar
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            work_type TEXT,
            topic TEXT,
            pages INTEGER,
            price INTEGER,
            status TEXT,
            file_path TEXT,
            created_at TEXT
        )
    """)

    # To'lovlar
    c.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            user_id INTEGER,
            amount INTEGER,
            status TEXT,
            screenshot_file_id TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


def ensure_files_dir():
    if not os.path.exists(FILES_DIR):
        os.makedirs(FILES_DIR)


def clean_text(text: str) -> str:
    """HTML/markdown belgilardan tozalash."""
    if not text:
        return ""
    return text.replace("<", "").replace(">", "").replace("&", "")


def get_or_create_user(message):
    """Foydalanuvchini olish yoki yaratish."""
    tg_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = (message.from_user.first_name or "") + " " + (message.from_user.last_name or "")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, free_used FROM users WHERE telegram_id = ?", (tg_id,))
    row = c.fetchone()

    if row:
        user_id, free_used = row
    else:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            INSERT INTO users (telegram_id, username, full_name, free_used, created_at)
            VALUES (?, ?, ?, 0, ?)
        """, (tg_id, username, full_name, now))
        conn.commit()
        user_id = c.lastrowid
        free_used = 0

    conn.close()
    return user_id, free_used


def increase_free_used(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE users SET free_used = free_used + 1 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_user_free_used(user_id: int) -> int:
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT free_used FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return int(row[0])
    return 0


def create_order(user_id, work_type, topic, pages, price, status="pending_payment"):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        INSERT INTO orders (user_id, work_type, topic, pages, price, status, file_path, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, work_type, topic, pages, price, status, "", now))
    conn.commit()
    order_id = c.lastrowid
    conn.close()
    return order_id


def update_order_status(order_id, status, file_path=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    if file_path is not None:
        c.execute("UPDATE orders SET status = ?, file_path = ? WHERE id = ?",
                  (status, file_path, order_id))
    else:
        c.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    conn.commit()
    conn.close()


def get_order(order_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT id, user_id, work_type, topic, pages, price, status, file_path
        FROM orders WHERE id = ?
    """, (order_id,))
    row = c.fetchone()
    conn.close()
    return row


def create_payment(order_id, user_id, amount, screenshot_file_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        INSERT INTO payments (order_id, user_id, amount, status, screenshot_file_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (order_id, user_id, amount, "pending", screenshot_file_id, now))
    conn.commit()
    payment_id = c.lastrowid
    conn.close()
    return payment_id


def get_payment(payment_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT id, order_id, user_id, amount, status, screenshot_file_id
        FROM payments WHERE id = ?
    """, (payment_id,))
    row = c.fetchone()
    conn.close()
    return row


def update_payment_status(payment_id, status):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE payments SET status = ? WHERE id = ?", (status, payment_id))
    conn.commit()
    conn.close()


# ============================
#      OPENAI GPT FUNKSIYA
# ============================

def ask_gpt(prompt: str, max_tokens: int = 2048) -> str:
    """GPT-4o-mini bilan matn generatsiyasi."""
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Sen talabalarga ilmiy-uslubda yordam beradigan yordamchi bo'lasan."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
        )
        return completion.choices[0].message.content
    except Exception as e:
        print("OpenAI xatosi:", e)
        return f"ERROR: {e}"


# ============================
#      FAYL YARATISH
# ============================

def create_pptx_from_text(topic: str, gpt_text: str, design_index: int = 1) -> str:
    """GPT matnidan PPTX yaratish."""
    ensure_files_dir()
    prs = Presentation()

    colors = [
        RGBColor(0, 102, 204),
        RGBColor(34, 139, 34),
        RGBColor(128, 0, 128),
        RGBColor(220, 20, 60),
        RGBColor(255, 140, 0),
        RGBColor(47, 79, 79),
    ]
    color = colors[(design_index - 1) % len(colors)]

    blocks = [b.strip() for b in gpt_text.split("\n\n") if b.strip()]
    if not blocks:
        blocks = [gpt_text]

    for block in blocks:
        slide_layout = prs.slide_layouts[5]  # blank
        slide = prs.slides.add_slide(slide_layout)

        # Fon
        bg = slide.shapes.add_shape(
            autoshape_type_id=1,
            left=Inches(0),
            top=Inches(0),
            width=Inches(13.3),
            height=Inches(7.5),
        )
        fill = bg.fill
        fill.solid()
        fill.fore_color.rgb = color
        bg.line.width = 0

        # Matn
        tx = slide.shapes.add_textbox(
            left=Inches(0.7),
            top=Inches(1),
            width=Inches(12),
            height=Inches(5.5),
        )
        tf = tx.text_frame
        tf.word_wrap = True

        lines = block.split("\n")
        title = lines[0][:80]
        body = "\n".join(lines[1:]) if len(lines) > 1 else ""

        p_title = tf.paragraphs[0]
        p_title.text = title
        p_title.font.size = Pt(36)
        p_title.font.bold = True
        p_title.font.color.rgb = RGBColor(255, 255, 255)
        p_title.alignment = PP_ALIGN.CENTER

        if body:
            p_body = tf.add_paragraph()
            p_body.text = body
            p_body.font.size = Pt(24)
            p_body.font.color.rgb = RGBColor(255, 255, 255)
            p_body.alignment = PP_ALIGN.LEFT

    filename = os.path.join(FILES_DIR, f"slayd_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pptx")
    prs.save(filename)
    return filename


def create_docx_from_text(title: str, gpt_text: str, work_type: str) -> str:
    """GPT matnidan DOCX yaratish."""
    ensure_files_dir()
    doc = Document()
    doc.add_heading(f"{work_type}: {title}", level=1)

    for block in gpt_text.split("\n\n"):
        block = block.strip()
        if block:
            doc.add_paragraph(block)

    filename = os.path.join(FILES_DIR, f"doc_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx")
    doc.save(filename)
    return filename


def generate_order_file(order_id: int) -> bool:
    """Buyurtma uchun fayl yaratadi va foydalanuvchiga yuboradi."""
    order = get_order(order_id)
    if not order:
        return False

    o_id, user_id, work_type, topic, pages, price, status, file_path = order
    topic = clean_text(topic)

    # chat_id ni topamiz
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return False
    chat_id = row[0]

    if work_type == "slayd":
        prompt = (
            f"Mavzu: {topic}\n"
            f"{pages} ta slayd uchun matn yoz. Har bir slaydda sarlavha va 3–6 ta punkt bo'lsin.\n"
            "Har bir slayd matnini ikki bo'sh qator bilan ajrat."
        )
        answer = ask_gpt(prompt, max_tokens=2048)
        if answer.startswith("ERROR:"):
            bot.send_message(chat_id, "AI xizmatida xato: " + answer[6:])
            return False

        filename = create_pptx_from_text(topic, answer, design_index=(pages % 6) + 1)
        update_order_status(order_id, "done", filename)
        with open(filename, "rb") as f:
            bot.send_document(chat_id, f, caption=f"Slayd tayyor!\nMavzu: {topic}")
        return True

    else:
        # referat / kurs ishi
        work_name = "Referat" if work_type == "referat" else "Kurs ishi"
        prompt = (
            f"Mavzu: {topic}\n"
            f"Taxminan {pages} betlik {work_name} matnini yoz. Kirish, asosiy qism va xulosani alohida bo'limlarda ber."
        )
        answer = ask_gpt(prompt, max_tokens=4096)
        if answer.startswith("ERROR:"):
            bot.send_message(chat_id, "AI xizmatida xato: " + answer[6:])
            return False

        filename = create_docx_from_text(topic, answer, work_name)
        update_order_status(order_id, "done", filename)
        with open(filename, "rb") as f:
            bot.send_document(chat_id, f, caption=f"{work_name} tayyor!\nMavzu: {topic}")
        return True


# ============================
#      MENYU
# ============================

def main_menu_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📝 Slayd", "📚 Kurs ishi")
    kb.row("📄 Mustaqil ish / Referat", "🧑‍🏫 Profi jamoa")
    kb.row("🎁 Referal bonus", "💰 Balans")
    kb.row("💵 To'lov / Hisob", "🌐 Til / Language", "❓ Yordam")
    return kb


MAIN_WORK_BUTTONS = [
    "📝 Slayd",
    "📄 Mustaqil ish / Referat",
    "📚 Kurs ishi",
]


# ============================
#      KOMANDALAR
# ============================

@bot.message_handler(commands=["start"])
def cmd_start(message):
    get_or_create_user(message)
    user_states[message.chat.id] = None

    text = (
        "Assalomu alaykum!\n\n"
        "Bu bot orqali slayd, mustaqil ish / referat va kurs ishini tez va qulay tayyorlab olishingiz mumkin.\n\n"
        f"Har bir foydalanuvchi uchun {MAX_FREE_LIMIT} ta buyurtma BEPUL.\n"
        f"Keyingi buyurtmalar (20 betgacha) narxi: {PRICE_PER_ORDER} so'm.\n\n"
        "Kerakli bo'limni menyudan tanlang."
    )
    bot.send_message(message.chat.id, text, reply_markup=main_menu_keyboard())


@bot.message_handler(commands=["help"])
def cmd_help(message):
    text = (
        "Yordam bo'limi:\n\n"
        "- Menyudagi tugmalar orqali xizmatni tanlang.\n"
        "- Slayd, referat/mustaqil ish yoki kurs ishlari bo'yicha buyurtma bering.\n"
        f"- {MAX_FREE_LIMIT} ta bepul buyurtma huquqiga egasiz.\n"
        "- To'lovdan so'ng chek skrinshotini yuboring, admin tasdiqlaydi.\n\n"
        f"Savollar uchun admin: {ADMIN_USERNAME}"
    )
    bot.send_message(message.chat.id, text, reply_markup=main_menu_keyboard())


@bot.message_handler(commands=["myid"])
def cmd_myid(message):
    bot.send_message(message.chat.id, f"Sening Telegram ID'ing: {message.from_user.id}")


@bot.message_handler(commands=["balance"])
def cmd_balance(message):
    handle_balance(message)


# ============================
#      MENYU BOSIMLARI
# ============================

@bot.message_handler(func=lambda m: m.text in MAIN_WORK_BUTTONS)
def handle_work_type(message):
    chat_id = message.chat.id

    mapping = {
        "📝 Slayd": "slayd",
        "📄 Mustaqil ish / Referat": "referat",
        "📚 Kurs ishi": "kurs ishi",
    }
    work_type = mapping.get(message.text)

    user_context[chat_id] = {"work_type": work_type}
    user_states[chat_id] = "enter_topic"

    bot.send_message(chat_id, "Mavzuni yozing:", reply_markup=types.ReplyKeyboardRemove())


@bot.message_handler(func=lambda m: m.text == "🧑‍🏫 Profi jamoa")
def handle_profi_team(message):
    text = (
        "Profi jamoa bo'limi:\n\n"
        "Murakkab kurs ishlar, diplom ishlari va boshqa maxsus buyurtmalar uchun "
        f"bevosita admin bilan bog'laning: {ADMIN_USERNAME}"
    )
    bot.send_message(message.chat.id, text)


@bot.message_handler(func=lambda m: m.text == "🎁 Referal bonus")
def handle_referal(message):
    text = (
        "Referal bonus tizimi tayyorlanmoqda.\n"
        "Kelajakda do'stlaringizni taklif qilib, bonuslar olish imkoniyati bo'ladi."
    )
    bot.send_message(message.chat.id, text)


@bot.message_handler(func=lambda m: m.text == "💰 Balans")
def handle_balance(message):
    user_id, _ = get_or_create_user(message)
    free_used = get_user_free_used(user_id)

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND status = 'done'", (user_id,))
    done = c.fetchone()[0]
    conn.close()

    text = (
        "Balans ma'lumotlari:\n\n"
        f"- Bepul buyurtmalardan foydalanilgan: {free_used} ta / {MAX_FREE_LIMIT} ta\n"
        f"- Yakunlangan buyurtmalar soni: {done}\n"
        f"- Har bir pullik buyurtma narxi: {PRICE_PER_ORDER} so'm (20 betgacha)."
    )
    bot.send_message(message.chat.id, text)


@bot.message_handler(func=lambda m: m.text == "💵 To'lov / Hisob")
def handle_payment_info(message):
    text = (
        "To'lov ma'lumotlari:\n\n"
        f"Karta: {CARD_NUMBER}\n"
        f"Ega: {CARD_OWNER}\n\n"
        "To'lovni amalga oshirgach, shu botga chek skrinshotini yuboring.\n"
        "Admin tasdiqlaganidan so'ng faylingiz tayyorlanadi."
    )
    bot.send_message(message.chat.id, text)


@bot.message_handler(func=lambda m: m.text == "🌐 Til / Language")
def handle_language(message):
    text = (
        "Hozircha bot faqat o'zbek tilida ishlaydi.\n"
        "Kelajakda rus va ingliz tillari qo'shilishi rejalashtirilgan."
    )
    bot.send_message(message.chat.id, text)


@bot.message_handler(func=lambda m: m.text == "❓ Yordam")
def handle_help_button(message):
    cmd_help(message)


# ============================
#      STATE-BASED HANDLERLAR
# ============================

@bot.message_handler(func=lambda m: user_states.get(m.chat.id) == "enter_topic")
def handle_topic(message):
    chat_id = message.chat.id
    ctx = user_context.get(chat_id, {})
    topic = clean_text(message.text.strip())
    ctx["topic"] = topic
    user_context[chat_id] = ctx

    work_type = ctx.get("work_type", "referat")
    if work_type == "slayd":
        bot.send_message(chat_id, "Nechta slayd kerak? (1–20):")
    else:
        bot.send_message(chat_id, "Taxminan necha bet kerak? (1–20):")

    user_states[chat_id] = "enter_pages"


@bot.message_handler(func=lambda m: user_states.get(m.chat.id) == "enter_pages")
def handle_pages(message):
    chat_id = message.chat.id
    ctx = user_context.get(chat_id, {})
    work_type = ctx.get("work_type", "referat")

    try:
        pages = int(message.text.strip())
        if not 1 <= pages <= MAX_PAGES_PER_ORDER:
            raise ValueError()
    except ValueError:
        bot.send_message(chat_id, f"Iltimos, 1 dan {MAX_PAGES_PER_ORDER} gacha bo'lgan son kiriting.")
        return

    ctx["pages"] = pages
    user_context[chat_id] = ctx

    user_id, _ = get_or_create_user(message)
    topic = ctx.get("topic", "")
    free_used = get_user_free_used(user_id)

    # Hali bepul limiti tugamagan bo'lsa
    if free_used < MAX_FREE_LIMIT:
        bot.send_message(chat_id, "Sizda bepul buyurtma mavjud. Buyurtma bepul bajariladi, kuting...")
        increase_free_used(user_id)
        order_id = create_order(user_id, work_type, topic, pages, 0, status="processing")
        ok = generate_order_file(order_id)
        if ok:
            bot.send_message(chat_id, "Bepul buyurtmangiz yakunlandi.", reply_markup=main_menu_keyboard())
        else:
            bot.send_message(chat_id, "Buyurtmani bajarishda xato yuz berdi.", reply_markup=main_menu_keyboard())
        user_states[chat_id] = None
        return

    # Pullik rejim
    price = PRICE_PER_ORDER
    order_id = create_order(user_id, work_type, topic, pages, price, status="pending_payment")
    ctx["order_id"] = order_id
    user_context[chat_id] = ctx
    user_states[chat_id] = "waiting_payment_screenshot"

    text = (
        "Buyurtma tafsilotlari:\n\n"
        f"- Turi: {work_type}\n"
        f"- Mavzu: {topic}\n"
        f"- Bet/slayd soni: {pages}\n"
        f"- Narx: {price} so'm\n\n"
        "Endi quyidagi kartaga to'lov qiling:\n"
        f"Karta: {CARD_NUMBER}\n"
        f"Ega: {CARD_OWNER}\n\n"
        "To'lovni tugatgach, shu chatga chek skrinshotini rasm ko'rinishida yuboring."
    )
    bot.send_message(chat_id, text)


# ============================
#      TO'LOV CHEKI (PHOTO)
# ============================

@bot.message_handler(content_types=["photo"])
def handle_payment_photo(message):
    chat_id = message.chat.id
    state = user_states.get(chat_id)

    if state != "waiting_payment_screenshot":
        bot.send_message(chat_id, "Bu rasm to'lov cheki sifatida qabul qilinmadi. Avval buyurtma yarating.")
        return

    ctx = user_context.get(chat_id, {})
    order_id = ctx.get("order_id")
    if not order_id:
        bot.send_message(chat_id, "Buyurtma ma'lumotlari topilmadi. Qayta urinib ko'ring.")
        user_states[chat_id] = None
        return

    order = get_order(order_id)
    if not order:
        bot.send_message(chat_id, "Buyurtma topilmadi. Qayta urinib ko'ring.")
        user_states[chat_id] = None
        return

    o_id, user_id, work_type, topic, pages, price, status, file_path = order

    file_id = message.photo[-1].file_id
    payment_id = create_payment(order_id, user_id, price, file_id)

    bot.send_message(chat_id, "Chek qabul qilindi. Admin tasdiqlaganidan so'ng fayl yaratiladi.")

    # Admin'ga yuborish
    try:
        caption = (
            "Yangi to'lov cheki\n\n"
            f"Payment ID: {payment_id}\n"
            f"Order ID: {order_id}\n"
            f"User ID: {user_id}\n"
            f"Username: @{message.from_user.username or 'no_username'}\n"
            f"Ish turi: {work_type}\n"
            f"Mavzu: {topic}\n"
            f"Bet/slayd: {pages}\n"
            f"Summa: {price} so'm\n\n"
            "Tasdiqlang yoki rad eting."
        )

        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"pay_ok_{payment_id}"),
            types.InlineKeyboardButton("❌ Rad etish", callback_data=f"pay_no_{payment_id}")
        )

        if ADMIN_TELEGRAM_ID:
            bot.send_photo(ADMIN_TELEGRAM_ID, file_id, caption=caption, reply_markup=kb)
        else:
            print("ADMIN_TELEGRAM_ID noto'g'ri yoki yo'q.")
    except Exception as e:
        print("Admin'ga chek yuborishda xato:", e)
        bot.send_message(
            chat_id,
            "Chekni admin ga yuborishda xato yuz berdi.\n"
            f"Iltimos, chekni bevosita adminga yuboring: {ADMIN_USERNAME}"
        )

    user_states[chat_id] = None


# ============================
#      ADMIN CALLBACK
# ============================

@bot.callback_query_handler(func=lambda c: c.data.startswith("pay_ok_") or c.data.startswith("pay_no_"))
def handle_payment_callback(call):
    if call.from_user.id != ADMIN_TELEGRAM_ID:
        bot.answer_callback_query(call.id, "Siz admin emassiz.")
        return

    data = call.data
    is_ok = data.startswith("pay_ok_")
    payment_id = int(data.split("_")[-1])

    payment = get_payment(payment_id)
    if not payment:
        bot.answer_callback_query(call.id, "To'lov topilmadi.")
        return

    p_id, order_id, user_id, amount, status, screenshot_file_id = payment
    order = get_order(order_id)
    if not order:
        bot.answer_callback_query(call.id, "Buyurtma topilmadi.")
        return

    o_id, u_id, work_type, topic, pages, price, o_status, file_path = order

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        bot.answer_callback_query(call.id, "Foydalanuvchi topilmadi.")
        return

    chat_id = row[0]

    if is_ok:
        update_payment_status(payment_id, "approved")
        update_order_status(order_id, "processing")
        bot.answer_callback_query(call.id, "To'lov tasdiqlandi. Fayl yaratilmoqda.")
        bot.send_message(chat_id, "To'lov tasdiqlandi. Faylingiz tayyorlanmoqda...")

        ok = generate_order_file(order_id)
        if ok:
            bot.send_message(chat_id, "Buyurtmangiz bajarildi.", reply_markup=main_menu_keyboard())
        else:
            bot.send_message(chat_id, "Fayl yaratishda xato yuz berdi.", reply_markup=main_menu_keyboard())
    else:
        update_payment_status(payment_id, "rejected")
        update_order_status(order_id, "payment_rejected")
        bot.answer_callback_query(call.id, "To'lov rad etildi.")
        bot.send_message(
            chat_id,
            "Admin to'lovni tasdiqlamadi. Iltimos, chekni tekshirib, kerak bo'lsa qayta yuboring.",
            reply_markup=main_menu_keyboard()
        )


# ============================
#      DEFAULT HANDLER
# ============================

@bot.message_handler(func=lambda m: True, content_types=["text"])
def fallback(message):
    if message.text.startswith("/"):
        bot.send_message(message.chat.id, "Bu buyruq hozircha qo'llab-quvvatlanmaydi.")
    else:
        bot.send_message(
            message.chat.id,
            "Kerakli bo'limni menyudan tanlang.",
            reply_markup=main_menu_keyboard()
        )


# ============================
#      BOTNI ISHGA TUSHIRISH
# ============================

if __name__ == "__main__":
    print("Super Talaba bot ishga tushmoqda...")
    print(f"ADMIN_TELEGRAM_ID = {ADMIN_TELEGRAM_ID}")
    init_db()
    ensure_files_dir()
    bot.infinity_polling(skip_pending=True)

