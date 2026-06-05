"""
FaylMasteruzbot — Aiogram v3 + SQLite3 asosida fayl konvertatsiya boti.
Olmos tizimi, keshbek, qariz va admin panel mavjud.
"""

import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)

# ─────────────────────────────────────────────
# SOZLAMALAR
# ─────────────────────────────────────────────

API_TOKEN = "8829983191:AAFYyNiSKHZRuZJxZW9sc3hzFB39eGT9OSY"
ADMIN_ID  = 8314283278
DB_PATH   = "faylmaster.db"

# Olmos sozlamalari
BOSHLANGICH_OLMOS  = 5     # Yangi foydalanuvchiga beriladigan olmos
MAX_OLMOS          = 100   # Maksimal olmos miqdori
KONVERTATSIYA_NARX = 1     # 1 konvertatsiya = 1 olmos
QARIZ_MIQDORI      = 1     # Qariz olish = +1 olmos
KESHBEK_OLMOS      = 1     # Keshbek kodi = +1 olmos

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# FSM HOLATLARI
# ─────────────────────────────────────────────

class KeshbekState(StatesGroup):
    """Keshbek kodi kiritish uchun FSM."""
    kod = State()

class AdminState(StatesGroup):
    """Admin paneli uchun FSM holatlari."""
    balans_user_id = State()   # Balans tahrirlash — user ID
    balans_miqdor  = State()   # Balans tahrirlash — yangi miqdor
    narx_yangi     = State()   # Narx o'zgartirish


# ─────────────────────────────────────────────
# MA'LUMOTLAR BAZASI
# ─────────────────────────────────────────────

def db_init() -> None:
    """Barcha jadvallarni yaratadi."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # Foydalanuvchilar jadvali
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id    INTEGER PRIMARY KEY,
            username   TEXT,
            full_name  TEXT,
            olmos      INTEGER  DEFAULT 5,
            qariz      INTEGER  DEFAULT 0,
            joined_at  TEXT     DEFAULT (datetime('now'))
        )
    """)

    # Keshbek kodlari jadvali (HisobchiXuzbot bilan integratsiya)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS keshbek_kodlar (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            kod         TEXT    UNIQUE NOT NULL,
            user_id     INTEGER NOT NULL,
            yaratilgan  TEXT    DEFAULT (datetime('now')),
            ishlatilgan INTEGER DEFAULT 0
        )
    """)

    # Konvertatsiyalar tarixi
    cur.execute("""
        CREATE TABLE IF NOT EXISTS konvertatsiyalar (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            fayl_nomi   TEXT,
            yaratilgan  TEXT    DEFAULT (datetime('now'))
        )
    """)

    # Sozlamalar jadvali (narxlar va boshqalar)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sozlamalar (
            kalit  TEXT PRIMARY KEY,
            qiymat TEXT
        )
    """)

    # Default sozlamalar
    cur.execute("""
        INSERT OR IGNORE INTO sozlamalar (kalit, qiymat)
        VALUES ('konvertatsiya_narx', '1')
    """)

    conn.commit()
    conn.close()


def user_register(user_id: int, username: str, full_name: str) -> bool:
    """
    Foydalanuvchini ro'yxatdan o'tkazadi.
    True — yangi foydalanuvchi, False — mavjud.
    """
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    mavjud = cur.fetchone()
    if not mavjud:
        cur.execute("""
            INSERT INTO users (user_id, username, full_name, olmos)
            VALUES (?, ?, ?, ?)
        """, (user_id, username, full_name, BOSHLANGICH_OLMOS))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False


def user_olish(user_id: int) -> dict | None:
    """Foydalanuvchi ma'lumotlarini qaytaradi."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        SELECT user_id, username, full_name, olmos, qariz
        FROM users WHERE user_id = ?
    """, (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {
            "user_id": row[0], "username": row[1],
            "full_name": row[2], "olmos": row[3], "qariz": row[4]
        }
    return None


def olmos_yangilash(user_id: int, miqdor: int) -> int:
    """
    Foydalanuvchi olmasini yangilaydi (qo'shish/ayirish).
    Yangi olmos miqdorini qaytaradi.
    """
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT olmos FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return 0
    yangi = min(max(0, row[0] + miqdor), MAX_OLMOS)
    cur.execute("UPDATE users SET olmos = ? WHERE user_id = ?", (yangi, user_id))
    conn.commit()
    conn.close()
    return yangi


def qariz_yangilash(user_id: int, miqdor: int) -> None:
    """Foydalanuvchi qarzini yangilaydi."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        UPDATE users SET qariz = qariz + ? WHERE user_id = ?
    """, (miqdor, user_id))
    conn.commit()
    conn.close()


def qariz_tozalash(user_id: int) -> None:
    """Foydalanuvchi qarzini nolga tushiradi."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("UPDATE users SET qariz = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def konvertatsiya_yozish(user_id: int, fayl_nomi: str) -> None:
    """Konvertatsiya tarixini bazaga yozadi."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO konvertatsiyalar (user_id, fayl_nomi)
        VALUES (?, ?)
    """, (user_id, fayl_nomi))
    conn.commit()
    conn.close()


def keshbek_kod_tekshir(kod: str) -> dict | None:
    """
    Keshbek kodni tekshiradi:
    - Mavjudligini
    - 48 soat ichida ekanligini
    - Ishlatilmaganligini
    Muvaffaqiyatli bo'lsa, kodni darhol o'chiradi.
    """
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # Kodni topish
    cur.execute("""
        SELECT id, user_id, yaratilgan, ishlatilgan
        FROM keshbek_kodlar
        WHERE kod = ?
    """, (kod,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return None

    kod_id, owner_id, yaratilgan_str, ishlatilgan = row

    # Ishlatilganligini tekshirish
    if ishlatilgan:
        conn.close()
        return None

    # 48 soat muddatini tekshirish
    try:
        yaratilgan = datetime.strptime(yaratilgan_str, "%Y-%m-%d %H:%M:%S")
        if datetime.now() - yaratilgan > timedelta(hours=48):
            # Muddati o'tgan — o'chirib yuborish
            cur.execute("DELETE FROM keshbek_kodlar WHERE id = ?", (kod_id,))
            conn.commit()
            conn.close()
            return None
    except Exception:
        conn.close()
        return None

    # Kodni ishlatilgan deb belgilash va darhol o'chirish
    cur.execute("DELETE FROM keshbek_kodlar WHERE id = ?", (kod_id,))
    conn.commit()
    conn.close()

    return {"kod_id": kod_id, "owner_id": owner_id}


def admin_balans_ozgartir(user_id: int, yangi_olmos: int) -> bool:
    """Admin tomonidan foydalanuvchi balansini o'zgartiradi."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cur.fetchone():
        conn.close()
        return False
    yangi = min(max(0, yangi_olmos), MAX_OLMOS)
    cur.execute("UPDATE users SET olmos = ? WHERE user_id = ?", (yangi, user_id))
    conn.commit()
    conn.close()
    return True


def sozlama_olish(kalit: str) -> str:
    """Sozlama qiymatini qaytaradi."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT qiymat FROM sozlamalar WHERE kalit = ?", (kalit,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else "1"


def sozlama_yangilash(kalit: str, qiymat: str) -> None:
    """Sozlama qiymatini yangilaydi."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO sozlamalar (kalit, qiymat)
        VALUES (?, ?)
    """, (kalit, qiymat))
    conn.commit()
    conn.close()


def admin_statistika() -> dict:
    """Admin uchun umumiy statistika."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    foydalanuvchilar = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM konvertatsiyalar")
    konvertatsiyalar = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users WHERE qariz > 0")
    qarzdorlar = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(SUM(olmos), 0) FROM users")
    jami_olmos = cur.fetchone()[0]
    conn.close()
    return {
        "foydalanuvchilar": foydalanuvchilar,
        "konvertatsiyalar": konvertatsiyalar,
        "qarzdorlar": qarzdorlar,
        "jami_olmos": jami_olmos,
    }


# ─────────────────────────────────────────────
# KLAVIATURA MENYULAR
# ─────────────────────────────────────────────

def asosiy_menyu(user: dict) -> ReplyKeyboardMarkup:
    """
    Foydalanuvchi holatiga qarab menyuni qaytaradi.
    Balans 0 bo'lsa 'Qariz olish' tugmasi qo'shiladi.
    """
    tugmalar = [
        [KeyboardButton(text="📁 Fayl yuborish")],
        [KeyboardButton(text="💎 Balansim"), KeyboardButton(text="💰 Keshbek olish")],
        [KeyboardButton(text="📊 Tarix"), KeyboardButton(text="❓ Yordam")],
    ]
    # Balans 0 bo'lsa qariz tugmasi
    if user.get("olmos", 0) == 0:
        tugmalar.append([KeyboardButton(text="🏦 Qariz olish")])

    return ReplyKeyboardMarkup(keyboard=tugmalar, resize_keyboard=True)


def admin_menyu() -> ReplyKeyboardMarkup:
    """Admin paneli menyusi."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Statistika")],
            [KeyboardButton(text="💎 Balans tahrirlash"), KeyboardButton(text="💲 Narx o'zgartirish")],
            [KeyboardButton(text="🔙 Orqaga")],
        ],
        resize_keyboard=True,
    )


# ─────────────────────────────────────────────
# BOT VA DISPATCHER
# ─────────────────────────────────────────────

bot = Bot(token=API_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())


# ─────────────────────────────────────────────
# YORDAMCHI: QARZDORLIK ESLATMASI
# ─────────────────────────────────────────────

async def qariz_eslatma(message: Message, user: dict) -> None:
    """Har safar kirganda qarzdorlikni eslatadi."""
    if user.get("qariz", 0) > 0:
        await message.answer(
            f"⚠️ <b>Sizda qarzdorlik bor!</b>\n"
            f"Qarz miqdori: <b>{user['qariz']} olmos</b>\n\n"
            "Keyingi konvertatsiyadan oldin qarzingiz to'lanadi.",
            parse_mode="HTML"
        )


# ─────────────────────────────────────────────
# HANDLERLAR — ASOSIY
# ─────────────────────────────────────────────

@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    """
    /start — foydalanuvchini ro'yxatdan o'tkazadi,
    yangi bo'lsa 5 olmos beradi.
    """
    u = message.from_user
    yangi = user_register(u.id, u.username or "", u.full_name or "")
    user  = user_olish(u.id)

    if yangi:
        xabar = (
            f"👋 Salom, <b>{u.full_name}</b>!\n\n"
            f"🎁 Sizga <b>{BOSHLANGICH_OLMOS} olmos</b> sovg'a!\n\n"
            "📁 <b>FaylMasterBot</b> — fayllarni konvertatsiya qiluvchi bot.\n"
            "Har konvertatsiya 1 olmos sarflaydi."
        )
    else:
        xabar = f"👋 Qaytib keldingiz, <b>{u.full_name}</b>!"

    await message.answer(xabar, reply_markup=asosiy_menyu(user), parse_mode="HTML")
    await qariz_eslatma(message, user)


@dp.message(Command("admin"))
async def admin_buyruq(message: Message) -> None:
    """Admin panelini ochadi (faqat ADMIN_ID uchun)."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Ruxsat yo'q.")
        return
    await message.answer(
        "🔐 <b>Admin paneli</b>\nNimani qilmoqchisiz?",
        reply_markup=admin_menyu(),
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────
# HANDLERLAR — BALANS
# ─────────────────────────────────────────────

@dp.message(F.text == "💎 Balansim")
async def balans_handler(message: Message) -> None:
    """Foydalanuvchi balansini ko'rsatadi."""
    user = user_olish(message.from_user.id)
    if not user:
        await message.answer("❌ Avval /start bosing.")
        return

    qariz_matn = f"\n⚠️ Qarz: <b>{user['qariz']} olmos</b>" if user['qariz'] > 0 else ""
    narx = sozlama_olish("konvertatsiya_narx")

    await message.answer(
        f"💎 <b>Balansingiz: {user['olmos']} olmos</b>{qariz_matn}\n\n"
        f"📌 1 konvertatsiya = <b>{narx} olmos</b>\n"
        f"📌 Maksimal: <b>{MAX_OLMOS} olmos</b>",
        reply_markup=asosiy_menyu(user),
        parse_mode="HTML"
    )
    await qariz_eslatma(message, user)


# ─────────────────────────────────────────────
# HANDLERLAR — FAYL YUBORISH (KONVERTATSIYA)
# ─────────────────────────────────────────────

@dp.message(F.text == "📁 Fayl yuborish")
async def fayl_yuborish_handler(message: Message) -> None:
    """Fayl yuborishga yo'naltiradi."""
    user = user_olish(message.from_user.id)
    narx = int(sozlama_olish("konvertatsiya_narx"))

    if user["olmos"] < narx and user["qariz"] >= 3:
        await message.answer(
            "❌ Balansingiz yetarli emas va qarizingiz limitga yetdi.\n"
            "Admin bilan bog'laning.",
            reply_markup=asosiy_menyu(user),
        )
        return

    await message.answer(
        f"📁 Konvertatsiya qilmoqchi bo'lgan faylni yuboring.\n"
        f"💎 Narxi: <b>{narx} olmos</b>\n"
        f"💎 Balansingiz: <b>{user['olmos']} olmos</b>",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML"
    )


@dp.message(F.document)
async def fayl_qabul(message: Message) -> None:
    """
    Faylni qabul qiladi, olmos yechadi,
    qayta ishlab bo'lgach faylni o'chiradi.
    """
    user = user_olish(message.from_user.id)
    if not user:
        await message.answer("❌ Avval /start bosing.")
        return

    narx = int(sozlama_olish("konvertatsiya_narx"))

    # Balans tekshirish
    if user["olmos"] < narx:
        if user["qariz"] < 3:
            # Qariz berish
            qariz_yangilash(message.from_user.id, narx)
            await message.answer(
                f"⚠️ Balansingiz yetmadi. <b>{narx} olmos</b> qariz olindi.\n"
                "Keyingi to'ldirganingizda avtomatik to'lanadi.",
                parse_mode="HTML"
            )
        else:
            await message.answer(
                "❌ Balansingiz yetarli emas!\n"
                "💰 Keshbek kodi kiriting yoki 🏦 Qariz oling.",
                reply_markup=asosiy_menyu(user),
            )
            return

    fayl = message.document
    fayl_nomi = fayl.file_name or "fayl"

    await message.answer(f"⏳ <b>{fayl_nomi}</b> qayta ishlanmoqda...", parse_mode="HTML")

    try:
        # Faylni yuklab olish
        fayl_info = await bot.get_file(fayl.file_id)
        yuklab_olish_yoli = f"/tmp/{fayl_nomi}"
        await bot.download_file(fayl_info.file_path, yuklab_olish_yoli)

        # ── BU YERGA FAYL KONVERTATSIYA LOGIKASINI QO'SHING ──
        # Masalan: PDF → Word, Image → PDF va h.k.
        # Hozircha faylni qaytarib yuboramiz (demo)
        await message.answer_document(
            document=fayl.file_id,
            caption=f"✅ <b>{fayl_nomi}</b> qayta ishlandi!",
            parse_mode="HTML"
        )

        # Faylni o'chirish (server tozalash)
        if os.path.exists(yuklab_olish_yoli):
            os.remove(yuklab_olish_yoli)
            logger.info(f"Fayl o'chirildi: {yuklab_olish_yoli}")

        # Olmos yechish va tarix yozish
        olmos_yangilash(message.from_user.id, -narx)
        konvertatsiya_yozish(message.from_user.id, fayl_nomi)

        # Qariz bo'lsa to'lash
        if user["qariz"] > 0:
            qariz_tozalash(message.from_user.id)
            await message.answer("✅ Qarzingiz to'landi!")

        yangi_user = user_olish(message.from_user.id)
        await message.answer(
            f"💎 Qolgan balansingiz: <b>{yangi_user['olmos']} olmos</b>",
            reply_markup=asosiy_menyu(yangi_user),
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Fayl xatosi: {e}")
        await message.answer(
            "❌ Faylni qayta ishlashda xato yuz berdi. Qayta urinib ko'ring.",
            reply_markup=asosiy_menyu(user),
        )


# ─────────────────────────────────────────────
# HANDLERLAR — KESHBEK
# ─────────────────────────────────────────────

@dp.message(F.text == "💰 Keshbek olish")
async def keshbek_boshlash(message: Message, state: FSMContext) -> None:
    """Keshbek kodi kiritish jarayonini boshlaydi."""
    await state.set_state(KeshbekState.kod)
    await message.answer(
        "💰 <b>Keshbek kodi kiriting:</b>\n\n"
        "Hisobchixuzbot'dan olgan 3 qatorli kodingizni yuboring.\n"
        "Masalan:\n<code>[AA12345678]\n[12345678]\n[ASDF]</code>",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML"
    )


@dp.message(KeshbekState.kod)
async def keshbek_kod_qabul(message: Message, state: FSMContext) -> None:
    """
    Kiritilgan keshbek kodni tekshiradi:
    - Bazada mavjudligi
    - 48 soat ichida ekanligini
    - Ishlatilmaganligini
    Muvaffaqiyatli bo'lsa 1 olmos qo'shadi va kodni o'chiradi.
    """
    kod = message.text.strip()
    user = user_olish(message.from_user.id)
    await state.clear()

    natija = keshbek_kod_tekshir(kod)

    if not natija:
        await message.answer(
            "❌ <b>Kod topilmadi yoki muddati o'tgan!</b>\n\n"
            "• Kod noto'g'ri kiritilgan bo'lishi mumkin\n"
            "• Kod allaqachon ishlatilgan\n"
            "• 48 soatlik muddat o'tgan",
            reply_markup=asosiy_menyu(user),
            parse_mode="HTML"
        )
        return

    # Olmos qo'shish
    yangi_olmos = olmos_yangilash(message.from_user.id, KESHBEK_OLMOS)
    yangi_user  = user_olish(message.from_user.id)

    await message.answer(
        f"✅ <b>Keshbek muvaffaqiyatli qo'shildi!</b>\n\n"
        f"💎 +{KESHBEK_OLMOS} olmos\n"
        f"💎 Yangi balans: <b>{yangi_olmos} olmos</b>",
        reply_markup=asosiy_menyu(yangi_user),
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────
# HANDLERLAR — QARIZ
# ─────────────────────────────────────────────

@dp.message(F.text == "🏦 Qariz olish")
async def qariz_olish(message: Message) -> None:
    """
    Balans 0 bo'lganda 1 olmos qariz beradi.
    Qarzi 3 dan oshsa rad etadi.
    """
    user = user_olish(message.from_user.id)

    if user["olmos"] > 0:
        await message.answer(
            "💎 Balansingizda olmos bor, qariz kerak emas!",
            reply_markup=asosiy_menyu(user),
        )
        return

    if user["qariz"] >= 3:
        await message.answer(
            "❌ Qariz limiti (3 olmos) to'lgan!\n"
            "Avval keshbek kodi orqali to'lang.",
            reply_markup=asosiy_menyu(user),
        )
        return

    # Qariz berish
    olmos_yangilash(message.from_user.id, QARIZ_MIQDORI)
    qariz_yangilash(message.from_user.id, QARIZ_MIQDORI)
    yangi_user = user_olish(message.from_user.id)

    await message.answer(
        f"🏦 <b>+{QARIZ_MIQDORI} olmos qariz olindi!</b>\n\n"
        f"💎 Balans: <b>{yangi_user['olmos']} olmos</b>\n"
        f"⚠️ Qarz: <b>{yangi_user['qariz']} olmos</b>",
        reply_markup=asosiy_menyu(yangi_user),
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────
# HANDLERLAR — TARIX
# ─────────────────────────────────────────────

@dp.message(F.text == "📊 Tarix")
async def tarix_handler(message: Message) -> None:
    """So'nggi konvertatsiyalar tarixini ko'rsatadi."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        SELECT fayl_nomi, yaratilgan FROM konvertatsiyalar
        WHERE user_id = ?
        ORDER BY id DESC LIMIT 10
    """, (message.from_user.id,))
    rows = cur.fetchall()
    conn.close()

    user = user_olish(message.from_user.id)

    if not rows:
        await message.answer(
            "📭 Hozircha konvertatsiya yo'q.",
            reply_markup=asosiy_menyu(user),
        )
        return

    qatorlar = ["📊 <b>So'nggi konvertatsiyalar:</b>\n"]
    for i, (nom, vaqt) in enumerate(rows, 1):
        qatorlar.append(f"{i}. 📄 {nom}\n   🕐 {vaqt}")

    await message.answer(
        "\n\n".join(qatorlar),
        reply_markup=asosiy_menyu(user),
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────
# HANDLERLAR — YORDAM
# ─────────────────────────────────────────────

@dp.message(F.text == "❓ Yordam")
async def yordam_handler(message: Message) -> None:
    """Yordam ma'lumotlarini ko'rsatadi."""
    user = user_olish(message.from_user.id)
    narx = sozlama_olish("konvertatsiya_narx")

    await message.answer(
        "❓ <b>FaylMasterBot — Yordam</b>\n\n"
        "💎 <b>Olmos tizimi:</b>\n"
        f"• Yangi foydalanuvchi: {BOSHLANGICH_OLMOS} olmos\n"
        f"• 1 konvertatsiya: {narx} olmos\n"
        f"• Maksimal: {MAX_OLMOS} olmos\n\n"
        "💰 <b>Keshbek:</b>\n"
        "• Hisobchixuzbot'dan kod oling\n"
        "• Kodni kiriting → +1 olmos\n"
        "• Kod 48 soat amal qiladi\n\n"
        "🏦 <b>Qariz:</b>\n"
        "• Balans 0 bo'lsa qariz olish mumkin\n"
        "• Maksimal 3 olmos qariz\n\n"
        "📁 <b>Fayl yuborish:</b>\n"
        "• Istalgan faylni yuboring\n"
        "• Bot qayta ishlab qaytaradi",
        reply_markup=asosiy_menyu(user),
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────
# ADMIN HANDLERLAR
# ─────────────────────────────────────────────

@dp.message(F.text == "👥 Statistika")
async def admin_stat(message: Message) -> None:
    """Admin statistikasini ko'rsatadi."""
    if message.from_user.id != ADMIN_ID:
        return
    stat = admin_statistika()
    narx = sozlama_olish("konvertatsiya_narx")
    await message.answer(
        "📊 <b>Admin statistika</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{stat['foydalanuvchilar']}</b>\n"
        f"📁 Konvertatsiyalar: <b>{stat['konvertatsiyalar']}</b>\n"
        f"⚠️ Qarzdorlar: <b>{stat['qarzdorlar']}</b>\n"
        f"💎 Jami olmos: <b>{stat['jami_olmos']}</b>\n"
        f"💲 Konvertatsiya narxi: <b>{narx} olmos</b>",
        parse_mode="HTML"
    )


@dp.message(F.text == "💎 Balans tahrirlash")
async def admin_balans_boshlash(message: Message, state: FSMContext) -> None:
    """Admin: foydalanuvchi balansini o'zgartirish."""
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminState.balans_user_id)
    await message.answer(
        "👤 Foydalanuvchi ID sini kiriting:",
        reply_markup=ReplyKeyboardRemove()
    )


@dp.message(AdminState.balans_user_id)
async def admin_balans_id(message: Message, state: FSMContext) -> None:
    try:
        user_id = int(message.text.strip())
        user = user_olish(user_id)
        if not user:
            await message.answer("❌ Foydalanuvchi topilmadi.")
            await state.clear()
            return
        await state.update_data(target_user_id=user_id)
        await state.set_state(AdminState.balans_miqdor)
        await message.answer(
            f"👤 {user['full_name']} (ID: {user_id})\n"
            f"💎 Hozirgi balans: {user['olmos']} olmos\n\n"
            "Yangi olmos miqdorini kiriting:"
        )
    except ValueError:
        await message.answer("❌ Noto'g'ri ID. Faqat raqam kiriting.")
        await state.clear()


@dp.message(AdminState.balans_miqdor)
async def admin_balans_miqdor(message: Message, state: FSMContext) -> None:
    try:
        yangi_olmos = int(message.text.strip())
        data = await state.get_data()
        target_id = data["target_user_id"]
        muvaffaq = admin_balans_ozgartir(target_id, yangi_olmos)
        await state.clear()
        if muvaffaq:
            await message.answer(
                f"✅ Balans yangilandi!\n"
                f"👤 ID: {target_id}\n"
                f"💎 Yangi balans: {min(yangi_olmos, MAX_OLMOS)} olmos",
                reply_markup=admin_menyu()
            )
        else:
            await message.answer("❌ Xato yuz berdi.", reply_markup=admin_menyu())
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting.")
        await state.clear()


@dp.message(F.text == "💲 Narx o'zgartirish")
async def admin_narx_boshlash(message: Message, state: FSMContext) -> None:
    """Admin: konvertatsiya narxini o'zgartirish."""
    if message.from_user.id != ADMIN_ID:
        return
    joriy = sozlama_olish("konvertatsiya_narx")
    await state.set_state(AdminState.narx_yangi)
    await message.answer(
        f"💲 Hozirgi narx: <b>{joriy} olmos</b>\n\nYangi narxni kiriting:",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML"
    )


@dp.message(AdminState.narx_yangi)
async def admin_narx_yangilash(message: Message, state: FSMContext) -> None:
    try:
        yangi_narx = int(message.text.strip())
        if yangi_narx < 1:
            raise ValueError
        sozlama_yangilash("konvertatsiya_narx", str(yangi_narx))
        await state.clear()
        await message.answer(
            f"✅ Narx yangilandi: <b>{yangi_narx} olmos</b>",
            reply_markup=admin_menyu(),
            parse_mode="HTML"
        )
    except ValueError:
        await message.answer("❌ Faqat musbat raqam kiriting.")
        await state.clear()


@dp.message(F.text == "🔙 Orqaga")
async def admin_orqaga(message: Message) -> None:
    """Admin panelidan chiqish."""
    if message.from_user.id != ADMIN_ID:
        return
    user = user_olish(message.from_user.id)
    await message.answer("✅ Asosiy menyuga qaytdingiz.", reply_markup=asosiy_menyu(user))


# ─────────────────────────────────────────────
# NOMA'LUM XABARLAR
# ─────────────────────────────────────────────

@dp.message()
async def notanish(message: Message, state: FSMContext) -> None:
    """FSM holati bo'lmagan noma'lum xabarlarga javob."""
    current = await state.get_state()
    if current:
        return
    user = user_olish(message.from_user.id)
    if not user:
        await message.answer("Boshlash uchun /start bosing.")
        return
    await message.answer(
        "🤔 Tushunmadim. Menyudan foydalaning:",
        reply_markup=asosiy_menyu(user),
    )


# ─────────────────────────────────────────────
# ASOSIY ISHGA TUSHIRISH
# ─────────────────────────────────────────────

async def main() -> None:
    """Botni ishga tushiradi."""
    db_init()
    logger.info("FaylMasterBot ishga tushdi ✅")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
