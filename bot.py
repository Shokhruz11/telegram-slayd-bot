import os
import time
import sqlite3
from datetime import datetime

import telebot
from telebot import types
from openai import OpenAI
from pptx import Presentation
from docx import Document

# ===========================
#  SOZLAMALAR (ENV DAN)
# ===========================

BOT_TOKEN = os.getenv("8552375519:AAGaLiTyCeiNH1sKmSqOyJo00Lc7ifYhLZw")  # Railway Shared Variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # OpenAI API key
ADMIN_ID = os.getenv("ADMIN_ID")  # ixtiyoriy
CARD_NUMBER = os.getenv("CARD_NUMBER", "4790 9200 1858 5070")
CARD_OWNER = os.getenv("CARD_OWNER", "Qo'chqorov Shohruz")
ADMIN_USERNAME = "@Shokhruz11"  # istasang env qilsa ham bo‘ladi

if ADMIN_ID is not None:
    try:
        ADMIN_ID = int(ADMIN_ID)
    except ValueError:
        ADMIN_ID = None

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env o'zgaruvchisi topilmadi")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY env o'zgaruvchisi topilmadi")

bot = telebot.TeleBot(BOT_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

# ===========================
#  BAZA: foydalanuvchilar
# ===========================

DB_PATH = "bot_users.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            free_used INTEGER DEFAULT 0,
            total_orders INTEGER DEFAULT 0,
            created_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def get_or_create_user(user):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, full_name, free_used, total_orders FROM users WHERE user_id = ?", (user.id,))
    row = cur.fetchone()
    if row is None:
        cur.execute(
            """
            INSERT INTO users (user_id, username, full_name, free_used, total_orders, created_at)
            VALUES (?, ?, ?, 0, 0, ?)
            """,
            (
                user.id,
                user.username or "",
                f"{user.first_name or ''} {user.last_name or ''}".strip(),
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        cur.execute(
            "SELECT user_id, username, full_name, free_used, total_orders FROM users WHERE user_id = ?",
            (user.id,),
        )
        row = cur.fetchone()
    conn.close()
    return {
        "user_id": row[0],
        "username": row[1],
        "full_name": row[2],
        "free_used": row[3],
        "total_orders": row[4],
    }


def mark_order_done(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET total_orders = total_orders + 1 WHERE user_id = ?", (user_id,))
    cur.execute("UPDATE users SET free_used = 1 WHERE user_id = ? AND free_used = 0", (user_id,))
    conn.commit()
    conn.close()


# ===========================
#  AI FUNKSIYALARI
# ===========================

def generate_ai_text(task_type: str, topic: str, extra_instruction: str = "") -> str:
    """
    task_type: 'slayd', 'mustaqil ish', 'referat', 'esse', 'test'
    """
    system_prompt = (
        "Siz O'zbek tilida talabalarga mo'ljallangan ilmiy-uslubdagi matnlar yaratasiz. "
        "Matn mantiqan bog'langan, aniq, plagiatsiz va tushunarli bo'lsin."
    )

    if task_type == "slayd":
        user_prompt = (
            f"Mavzu: {topic}\n\n"
            "PowerPoint slayd uchun reja va punktlar yozing. "
            "Har bir fikr yangi satrda bo'lsin. Keraksiz kirish gaplarsiz, faqat asosiy punktlar. "
            "Punkt boshiga '-' yoki '•' belgisi qo'ying.\n\n"
            + extra_instruction
        )
    elif task_type in ("mustaqil", "referat", "esse"):
        user_prompt = (
            f"Mavzu: {topic}\n\n"
            "Talaba uchun taxminan 5-8 betga teng bo'lgan uzluksiz matn yozing. "
            "Kirish, asosiy qism va xulosaga bo'linib, lekin sarlavhasiz, oddiy uzluksiz matn bo'lib ketsin. "
            "Konkret faktlar, misollar, ilmiy iboralar bo'lsin.\n\n"
            + extra_instruction
        )
    elif task_type == "test":
        user_prompt = (
            f"Mavzu: {topic}\n\n"
            "Talabalar uchun 20 ta test savoli tuzing. Har bir savolda 4 ta javob varianti bo'lsin (A, B, C, D). "
            "Javoblarni alohida ro'yxatda 'To'g'ri javoblar:' deb yozib chiqing.\n\n"
            + extra_instruction
        )
    else:
        user_prompt = f"Mavzu: {topic}\n\n{extra_instruction}"

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
    )

    return response.choices[0].message.content


# ===========================
#  FAYL YARATISH FUNKSIYALARI
# ===========================

def create_pptx_from_text(topic: str, content: str, filename: str):
    prs = Presentation()
    slide_layout = prs.slide_layouts[1]  # Title and Content

    slide = prs.slides.add_slide(slide_layout)
    title_placeholder = slide.shapes.title
    body = slide.placeholders[1].text_frame

    title_placeholder.text = topic
    body.clear()

    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line[0] in "-•":
            line = line[1:].strip()
        p = body.add_paragraph()
        p.text = line
        p.level = 0

    prs.save(filename)
    return filename


def create_docx_from_text(topic: str, content: str, filename: str):
    doc = Document()
    doc.add_heading(topic, level=1)
    for para in content.split("\n"):
        para = para.strip()
        if not para:
            continue
        doc.add_paragraph(para)
    doc.save(filename)
    return filename


# ===========================
#  MENULAR
# ===========================

def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    row1 = [types.KeyboardButton("🖥 Slayd (PPTX)"), types.KeyboardButton("📄 Mustaqil ish (DOCX)")]
    row2 = [types.KeyboardButton("📚 Referat (DOCX)"), types.KeyboardButton("✍️ Esse (DOCX)")]
    row3 = [types.KeyboardButton("❓ Test tuzish"), types.KeyboardButton("📘 Kurs ishi / Diplom ishi")]
    row4 = [types.KeyboardButton("👥 Professionallar jamoasi"), types.KeyboardButton("ℹ️ Yordam")]
    row5 = [types.KeyboardButton("💰 To'lov va narxlar"), types.KeyboardButton("📊 Mening buyurtmalarim")]
    markup.add(*row1)
    markup.add(*row2)
    markup.add(*row3)
    markup.add(*row4)
    markup.add(*row5)
    return markup


# ===========================
#  HANDLERLAR
# ===========================

@bot.message_handler(commands=["start"])
def start_handler(message):
    init_db()
    user = get_or_create_user(message.from_user)
    text = (
        "Assalomu alaykum! 👋\n\n"
        "Bu bot orqali talabalar uchun quyidagi ishlarni AI yordamida tez va sifatli tayyorlab olishingiz mumkin:\n"
        "• Slayd (PowerPoint)\n"
        "• Mustaqil ish\n"
        "• Referat\n"
        "• Esse\n"
        "• Test savollari\n\n"
        "✅ Har bir yangi foydalanuvchi uchun 1 marta BEPUL xizmat.\n"
        "Keyingi buyurtmalar: 20 listgacha 5000 so'm.\n\n"
        f"Agar savolingiz bo'lsa, admin: {ADMIN_USERNAME}"
    )
    bot.send_message(message.chat.id, text, reply_markup=main_menu())


@bot.message_handler(func=lambda m: m.text == "💰 To'lov va narxlar")
def payment_info(message):
    text = (
        "💰 *To'lov va narxlar*\n\n"
        "• 1-bor buyurtma — BEPUL ✅\n"
        "• Keyingi buyurtmalar — 20 listgacha 5000 so'm.\n\n"
        "To'lov uchun karta ma'lumotlari:\n"
        f"💳 Karta: `{CARD_NUMBER}`\n"
        f"👤 Egasi: *{CARD_OWNER}*\n\n"
        f"To'lovdan so'ng chekni admin {ADMIN_USERNAME} ga yuboring."
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "ℹ️ Yordam")
def help_handler(message):
    text = (
        "ℹ️ *Yordam*\n\n"
        "1. Kerakli menuni tanlang (Slayd, Mustaqil ish, Referat, Esse, Test).\n"
        "2. Bot sizdan mavzuni so'raydi.\n"
        "3. AI matn yaratadi va uni PPTX yoki DOCX formatida yuboradi.\n\n"
        "1-marta buyurtma bepul, keyingi safar 5000 so'm.\n"
        f"Qo'shimcha savollar bo'lsa, admin bilan bog'laning: {ADMIN_USERNAME}"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "📊 Mening buyurtmalarim")
def my_orders(message):
    init_db()
    user = get_or_create_user(message.from_user)
    text = (
        "📊 *Statistika*\n\n"
        f"👤 Foydalanuvchi: {user['full_name'] or message.from_user.first_name}\n"
        f"🆔 ID: {user['user_id']}\n"
        f"🔁 Jami buyurtmalar: {user['total_orders']}\n"
        f"🎁 Bepul imkoniyat ishlatilganmi: {'Ha' if user['free_used'] else 'Yo‘q'}\n\n"
        "Eslatma: 1-bor bepul, keyingi buyurtmalar 5000 so'm."
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "📘 Kurs ishi / Diplom ishi")
def kurs_ishi_handler(message):
    text = (
        "📘 Kurs ishi va diplom ishlari bo‘yicha tayyorlash, tahlil qilish va tuzatish xizmatlari "
        f"admin orqali amalga oshiriladi.\n\nAloqa: {ADMIN_USERNAME}\n\n"
        "❗ Narxlar va muddatlar bo‘yicha admin bilan kelishiladi."
    )
    bot.send_message(message.chat.id, text)


@bot.message_handler(func=lambda m: m.text == "👥 Professionallar jamoasi")
def prof_team_handler(message):
    text = (
        "👥 *Professionallar jamoasi*\n\n"
        "Kurs ishi, diplom ishi, prezentatsiya va boshqa murakkab topshiriqlarni "
        "tajribali jamoa bajarib beradi.\n\n"
        f"Bog'lanish: {ADMIN_USERNAME}\n\n"
        "Telegram guruhi yoki kanal manzili bo'lsa, shu yerga qo'shish mumkin."
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


# ===== BOSQICHLI GENERATSIYA =====

@bot.message_handler(func=lambda m: m.text == "🖥 Slayd (PPTX)")
def ask_slide_topic(message):
    msg = bot.send_message(message.chat.id, "🖥 Qaysi mavzuda slayd kerak? Mavzuni yozing:")
    bot.register_next_step_handler(msg, generate_slide)


def generate_slide(message):
    init_db()
    user = get_or_create_user(message.from_user)
    topic = message.text.strip()
    bot.send_message(message.chat.id, "⏳ Slayd tayyorlanmoqda...")

    try:
        content = generate_ai_text("slayd", topic)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Xatolik: {e}")
        return

    filename = f"slayd_{message.chat.id}_{int(time.time())}.pptx"
    create_pptx_from_text(topic, content, filename)

    mark_order_done(user["user_id"])

    caption = build_caption_after_order(user["user_id"], "Slayd (PPTX)")
    with open(filename, "rb") as f:
        bot.send_document(message.chat.id, f, visible_file_name=filename, caption=caption)


@bot.message_handler(func=lambda m: m.text == "📄 Mustaqil ish (DOCX)")
def ask_mustaqil_topic(message):
    msg = bot.send_message(message.chat.id, "📄 Qaysi mavzuda mustaqil ish kerak? Mavzuni yozing:")
    bot.register_next_step_handler(msg, generate_mustaqil)


def generate_mustaqil(message):
    init_db()
    user = get_or_create_user(message.from_user)
    topic = message.text.strip()
    bot.send_message(message.chat.id, "⏳ Mustaqil ish tayyorlanmoqda...")

    try:
        content = generate_ai_text("mustaqil", topic)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Xatolik: {e}")
        return

    filename = f"mustaqil_{message.chat.id}_{int(time.time())}.docx"
    create_docx_from_text(topic, content, filename)

    mark_order_done(user["user_id"])

    caption = build_caption_after_order(user["user_id"], "Mustaqil ish (DOCX)")
    with open(filename, "rb") as f:
        bot.send_document(message.chat.id, f, visible_file_name=filename, caption=caption)


@bot.message_handler(func=lambda m: m.text == "📚 Referat (DOCX)")
def ask_referat_topic(message):
    msg = bot.send_message(message.chat.id, "📚 Qaysi mavzuda referat kerak? Mavzuni yozing:")
    bot.register_next_step_handler(msg, generate_referat)


def generate_referat(message):
    init_db()
    user = get_or_create_user(message.from_user)
    topic = message.text.strip()
    bot.send_message(message.chat.id, "⏳ Referat tayyorlanmoqda...")

    try:
        content = generate_ai_text("referat", topic)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Xatolik: {e}")
        return

    filename = f"referat_{message.chat.id}_{int(time.time())}.docx"
    create_docx_from_text(topic, content, filename)

    mark_order_done(user["user_id"])

    caption = build_caption_after_order(user["user_id"], "Referat (DOCX)")
    with open(filename, "rb") as f:
        bot.send_document(message.chat.id, f, visible_file_name=filename, caption=caption)


@bot.message_handler(func=lambda m: m.text == "✍️ Esse (DOCX)")
def ask_esse_topic(message):
    msg = bot.send_message(message.chat.id, "✍️ Qaysi mavzuda esse kerak? Mavzuni yozing:")
    bot.register_next_step_handler(msg, generate_esse)


def generate_esse(message):
    init_db()
    user = get_or_create_user(message.from_user)
    topic = message.text.strip()
    bot.send_message(message.chat.id, "⏳ Esse tayyorlanmoqda...")

    try:
        content = generate_ai_text("esse", topic)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Xatolik: {e}")
        return

    filename = f"esse_{message.chat.id}_{int(time.time())}.docx"
    create_docx_from_text(topic, content, filename)

    mark_order_done(user["user_id"])

    caption = build_caption_after_order(user["user_id"], "Esse (DOCX)")
    with open(filename, "rb") as f:
        bot.send_document(message.chat.id, f, visible_file_name=filename, caption=caption)


@bot.message_handler(func=lambda m: m.text == "❓ Test tuzish")
def ask_test_topic(message):
    msg = bot.send_message(message.chat.id, "❓ Qaysi mavzudan test tuzaylik? Mavzuni yozing:")
    bot.register_next_step_handler(msg, generate_test)


def generate_test(message):
    init_db()
    user = get_or_create_user(message.from_user)
    topic = message.text.strip()
    bot.send_message(message.chat.id, "⏳ Test savollari tayyorlanmoqda...")

    try:
        content = generate_ai_text("test", topic)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Xatolik: {e}")
        return

    filename = f"test_{message.chat.id}_{int(time.time())}.docx"
    create_docx_from_text(f"Test savollari: {topic}", content, filename)

    mark_order_done(user["user_id"])

    caption = build_caption_after_order(user["user_id"], "Test (DOCX)")
    with open(filename, "rb") as f:
        bot.send_document(message.chat.id, f, visible_file_name=filename, caption=caption)


# ===========================
#  BUYURTMA XABAR CAPTIONI
# ===========================

def build_caption_after_order(user_id: int, service_name: str) -> str:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT free_used, total_orders FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()

    free_used = row[0] if row else 1
    total_orders = row[1] if row else 1

    if free_used == 0:
        return (
            f"✅ {service_name} tayyor.\n\n"
            "Bu sizning 1-bor BEPUL buyurtmangiz edi. 🎁\n"
            "Keyingi buyurtmalarda xizmat narxi: 20 listgacha 5000 so'm.\n\n"
            f"To'lov uchun karta: {CARD_NUMBER} ({CARD_OWNER})."
        )
    else:
        return (
            f"✅ {service_name} tayyor.\n\n"
            f"Jami buyurtmalaringiz: {total_orders}\n"
            "Eslatma: xizmat narxi 20 listgacha 5000 so'm.\n"
            f"To'lov uchun karta: {CARD_NUMBER} ({CARD_OWNER}).\n"
            f"To'lovni amalga oshirgach, chekni {ADMIN_USERNAME} ga yuboring."
        )


# ===========================
#  BOTNI ISHGA TUSHIRISH
# ===========================

if __name__ == "__main__":
    init_db()
    print("🚀 Bot ishga tushdi")
    bot.polling(none_stop=True, interval=0, timeout=20)


