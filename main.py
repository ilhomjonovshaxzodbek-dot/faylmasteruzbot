"""
FaylMasteruzbot v2.0 — Aiogram v3 + SQLite3
Yangi: Referal, Kunlik bonus, Top reyting, VIP status, Olmos sovg'a
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

API_TOKEN = "BU YERGA YANGI TOKENINGNI YOZASAN"
ADMIN_ID  = 8314283278
DB_PATH   = "faylmaster.db"

# Olmos sozlamalari
BOSHLANGICH_OLMOS = 5      # Yangi foydalanuvchiga
MAX_OLMOS         = 100    # Maksimal
KONVERTATSIYA_NARX = 1     # 1 fayl = 1 olmos
QARIZ_MIQDORI     = 1      # Qariz = +1 olmos
KESHBEK_OLMOS     = 1      # Keshbek kodi = +1 olmos
REFERAL_OLMOS     = 2      # Do'st taklif = +2 olmos
KUNLIK_BONUS      = 1      # Kunlik bonus = +1 olmos
SOVGA_MIN         = 1      # Sovg'a uchun minimal olmos
VIP_CHEGARA       = 50     # VIP status uchun olmos miqdori

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# FSM HOLATLARI
# ─────────────────────────────────────────────

class KeshbekState(StatesGroup):
    kod = State()

class SovgaState(StatesGroup):
    user_id  = State()   # Kimga sovg'a
    miqdor   = State()   # Qancha olmos

class AdminState(StatesGroup):
    balans_user_id = State()
    balans_miqdor  = State()
    narx_yangi     = State()
    xabar_matn     = State()   # Hammaga xabar yuborish


# ─────────────────────────────────────────────
# MA'LUMOTLAR BAZASI
# ─────────────────────────────────────────────

def db_init() -> None:
    """Barcha jadvallarni yaratadi va yangi ustunlarni qo'shadi."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # Foydalanuvchilar jadvali
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id        INTEGER PRIMARY KEY,
            username       TEXT,
            full_name      TEXT,
            olmos          INTEGER DEFAULT 5,
            qariz          INTEGER DEFAULT 0,
            referal_kodi   TEXT    UNIQUE,
            referal_kimdan INTEGER DEFAULT NULL,
            kunlik_bonus   TEXT    DEFAULT NULL,
            joined_at      TEXT    DEFAULT (datetime('now'))
        )
    """)

    # Keshbek kodlari (HisobchiXuzbot integratsiya)
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
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            fayl_nomi  TEXT,
            yaratilgan TEXT    DEFAULT (datetime('now'))
        )
    """)

    # Sovg'alar tarixi
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sovgalar (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            kimdan     INTEGER NOT NULL,
            kimga      INTEGER NOT NULL,
            miqdor     INTEGER NOT NULL,
            yaratilgan TEXT    DEFAULT (datetime('now'))
        )
    """)

    # Sozlamalar
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sozlamalar (
            kalit  TEXT PRIMARY KEY,
            qiymat TEXT
        )
    """)

    cur.execute("INSERT OR IGNORE INTO sozlamalar (kalit, qiymat) VALUES ('konvertatsiya_narx', '1')")

    conn.commit()
    conn.close()


def referal_kod_yarat(user_id: int) -> str:
    """Foydalanuvchi uchun noyob referal kodi yaratadi."""
    import random, string
    harflar = string.ascii_uppercase + string.digits
    kod = "REF" + "".join(random.choices(harflar, k=7))
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("UPDATE users SET referal_kodi = ? WHERE user_id = ?", (kod, user_id))
    conn.commit()
    conn.close()
    return kod


def user_register(user_id: int, username: str, full_name: str, referal_kimdan: int = None) -> bool:
    """
    Foydalanuvchini ro'yxatdan o'tkazadi.
    referal_kimdan — kim taklif qilgani (ID).
    True — yangi, False — mavjud.
    """
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if cur.fetchone():
        conn.close()
        return False

    cur.execute("""
        INSERT INTO users (user_id, username, full_name, olmos, referal_kimdan)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, username, full_name, BOSHLANGICH_OLMOS, referal_kimdan))

    conn.commit()
    conn.close()

    # Referal kodi yaratish
    referal_kod_yarat(user_id)

    # Taklif qilgan kishiga olmos berish
    if referal_kimdan:
        olmos_yangilash(referal_kimdan, REFERAL_OLMOS)

    return True


def user_olish(user_id: int) -> dict | None:
    """Foydalanuvchi ma'lumotlarini qaytaradi."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        SELECT user_id, username, full_name, olmos, qariz, referal_kodi, kunlik_bonus
        FROM users WHERE user_id = ?
    """, (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {
            "user_id": row[0], "username": row[1], "full_name": row[2],
            "olmos": row[3], "qariz": row[4], "referal_kodi": row[5],
            "kunlik_bonus": row[6]
        }
    return None


def user_referal_koddan_topish(kod: str) -> dict | None:
    """Referal kodi bo'yicha foydalanuvchini topadi."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT user_id, full_name FROM users WHERE referal_kodi = ?", (kod,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {"user_id": row[0], "full_name": row[1]}
    return None


def olmos_yangilash(user_id: int, miqdor: int) -> int:
    """Olmasni yangilaydi. Yangi miqdorni qaytaradi."""
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
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("UPDATE users SET qariz = qariz + ? WHERE user_id = ?", (miqdor, user_id))
    conn.commit()
    conn.close()


def qariz_tozalash(user_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("UPDATE users SET qariz = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def kunlik_bonus_tekshir(user_id: int) -> bool:
    """
    Kunlik bonusni tekshiradi.
    True — bonus olish mumkin, False — bugun allaqachon olgan.
    """
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT kunlik_bonus FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()

    if not row or not row[0]:
        return True  # Hech qachon olmagan

    try:
        oxirgi = datetime.strptime(row[0], "%Y-%m-%d")
        return datetime.now().date() > oxirgi.date()
    except Exception:
        return True


def kunlik_bonus_belgilash(user_id: int) -> None:
    """Bugungi kunlik bonus vaqtini bazaga yozadi."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    bugun = datetime.now().strftime("%Y-%m-%d")
    cur.execute("UPDATE users SET kunlik_bonus = ? WHERE user_id = ?", (bugun, user_id))
    conn.commit()
    conn.close()


def top_foydalanuvchilar(limit: int = 10) -> list:
    """Eng ko'p olmosli foydalanuvchilar ro'yxati."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        SELECT full_name, username, olmos FROM users
        ORDER BY olmos DESC LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows


def referal_soni(user_id: int) -> int:
    """Foydalanuvchi nechta do'st taklif qilganini qaytaradi."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE referal_kimdan = ?", (user_id,))
    soni = cur.fetchone()[0]
    conn.close()
    return soni


def sovga_yuborish(kimdan: int, kimga: int, miqdor: int) -> bool:
    """
    Bir foydalanuvchidan boshqasiga olmos sovg'a qiladi.
    Muvaffaqiyatli bo'lsa True qaytaradi.
    """
    kimdan_user = user_olish(kimdan)
    kimga_user  = user_olish(kimga)

    if not kimdan_user or not kimga_user:
        return False
    if kimdan_user["olmos"] < miqdor:
        return False
    if miqdor < SOVGA_MIN:
        return False

    olmos_yangilash(kimdan, -miqdor)
    olmos_yangilash(kimga,  +miqdor)

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO sovgalar (kimdan, kimga, miqdor)
        VALUES (?, ?, ?)
    """, (kimdan, kimga, miqdor))
    conn.commit()
    conn.close()
    return True


def keshbek_kod_tekshir(kod: str) -> dict | None:
    """Keshbek kodni tekshirib, to'g'ri bo'lsa o'chiradi."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        SELECT id, user_id, yaratilgan, ishlatilgan
        FROM keshbek_kodlar WHERE kod = ?
    """, (kod,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return None

    kod_id, owner_id, yaratilgan_str, ishlatilgan = row

    if ishlatilgan:
        conn.close()
        return None

    try:
        yaratilgan = datetime.strptime(yaratilgan_str, "%Y-%m-%d %H:%M:%S")
        if datetime.now() - yaratilgan > timedelta(hours=48):
            cur.execute("DELETE FROM keshbek_kodlar WHERE id = ?", (kod_id,))
            conn.commit()
            conn.close()
            return None
    except Exception:
        conn.close()
        return None

    cur.execute("DELETE FROM keshbek_kodlar WHERE id = ?", (kod_id,))
    conn.commit()
    conn.close()
    return {"kod_id": kod_id, "owner_id": owner_id}


def konvertatsiya_yozish(user_id: int, fayl_nomi: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("INSERT INTO konvertatsiyalar (user_id, fayl_nomi) VALUES (?, ?)", (user_id, fayl_nomi))
    conn.commit()
    conn.close()


def admin_balans_ozgartir(user_id: int, yangi_olmos: int) -> bool:
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
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT qiymat FROM sozlamalar WHERE kalit = ?", (kalit,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else "1"


def sozlama_yangilash(kalit: str, qiymat: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO sozlamalar (kalit, qiymat) VALUES (?, ?)", (kalit, qiymat))
    conn.commit()
    conn.close()


def admin_statistika() -> dict:
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    foydalanuvchilar = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM konvertatsiyalar")
    konvertatsiyalar = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users WHERE qariz > 0")
    qarzdorlar = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*) FROM users WHERE olmos >= {VIP_CHEGARA}")
    viplar = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(SUM(olmos), 0) FROM users")
    jami_olmos = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM sovgalar")
    sovgalar = cur.fetchone()[0]
    conn.close()
    return {
        "foydalanuvchilar": foydalanuvchilar,
        "konvertatsiyalar": konvertatsiyalar,
        "qarzdorlar": qarzdorlar,
        "viplar": viplar,
        "jami_olmos": jami_olmos,
        "sovgalar": sovgalar,
    }


def barcha_userlar() -> list:
    """Admin — hammaga xabar yuborish uchun user_id lar ro'yxati."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


# ─────────────────────────────────────────────
# YORDAMCHI: VIP TEKSHIRISH
# ─────────────────────────────────────────────

def vip_mi(olmos: int) -> bool:
    return olmos >= VIP_CHEGARA


# ─────────────────────────────────────────────
# KLAVIATURA MENYULAR
# ─────────────────────────────────────────────

def asosiy_menyu(user: dict) -> ReplyKeyboardMarkup:
    """Foydalanuvchi holatiga qarab menyu."""
    vip_belgi = "👑 " if vip_mi(user.get("olmos", 0)) else ""
    tugmalar = [
        [KeyboardButton(text="📁 Fayl yuborish")],
        [KeyboardButton(text=f"💎 {vip_belgi}Balansim"), KeyboardButton(text="💰 Keshbek olish")],
        [KeyboardButton(text="🎁 Kunlik bonus"), KeyboardButton(text="👥 Referal")],
        [KeyboardButton(text="🎀 Sovg'a yuborish"), KeyboardButton(text="🏆 Top reyting")],
        [KeyboardButton(text="📊 Tarix"), KeyboardButton(text="❓ Yordam")],
    ]
    if user.get("olmos", 0) == 0:
        tugmalar.append([KeyboardButton(text="🏦 Qariz olish")])
    return ReplyKeyboardMarkup(keyboard=tugmalar, resize_keyboard=True)


def admin_menyu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Statistika")],
            [KeyboardButton(text="💎 Balans tahrirlash"), KeyboardButton(text="💲 Narx o'zgartirish")],
            [KeyboardButton(text="📢 Hammaga xabar")],
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
# YORDAMCHI FUNKSIYALAR
# ─────────────────────────────────────────────

async def qariz_eslatma(message: Message, user: dict) -> None:
    if user.get("qariz", 0) > 0:
        await message.answer(
            f"⚠️ <b>Sizda {user['qariz']} olmos qarzdorlik bor!</b>",
            parse_mode="HTML"
        )


# ─────────────────────────────────────────────
# HANDLERLAR — START (REFERAL QO'LLAB-QUVVATLASH)
# ─────────────────────────────────────────────

@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    """
    /start yoki /start REF1234567 — referal tizimi.
    Yangi foydalanuvchiga 5 olmos, taklif qilganga +2 olmos.
    """
    u = message.from_user
    referal_kimdan = None

    # /start REF1234567 formatini tekshirish
    args = message.text.split()
    if len(args) > 1:
        kod = args[1].strip()
        taklif_qilgan = user_referal_koddan_topish(kod)
        if taklif_qilgan and taklif_qilgan["user_id"] != u.id:
            referal_kimdan = taklif_qilgan["user_id"]

    yangi = user_register(u.id, u.username or "", u.full_name or "", referal_kimdan)
    user  = user_olish(u.id)

    if yangi:
        if referal_kimdan:
            taklif_user = user_olish(referal_kimdan)
            xabar = (
                f"👋 Salom, <b>{u.full_name}</b>!\n\n"
                f"🎁 Sizga <b>{BOSHLANGICH_OLMOS} olmos</b> sovg'a!\n"
                f"✅ <b>{taklif_user['full_name']}</b> taklifi orqali keldingiz.\n\n"
                "📁 FaylMasterBot — fayllarni konvertatsiya qiluvchi bot!"
            )
            # Taklif qilganga xabar yuborish
            try:
                await bot.send_message(
                    referal_kimdan,
                    f"🎉 <b>{u.full_name}</b> sizning havolangiz orqali qo'shildi!\n"
                    f"💎 +{REFERAL_OLMOS} olmos hisoblandi!",
                    parse_mode="HTML"
                )
            except Exception:
                pass
        else:
            xabar = (
                f"👋 Salom, <b>{u.full_name}</b>!\n\n"
                f"🎁 Sizga <b>{BOSHLANGICH_OLMOS} olmos</b> sovg'a!\n\n"
                "📁 FaylMasterBot — fayllarni konvertatsiya qiluvchi bot.\n"
                "Har konvertatsiya 1 olmos sarflaydi."
            )
    else:
        vip_matn = " 👑 VIP" if vip_mi(user["olmos"]) else ""
        xabar = f"👋 Qaytib keldingiz, <b>{u.full_name}</b>{vip_matn}!"

    await message.answer(xabar, reply_markup=asosiy_menyu(user), parse_mode="HTML")
    await qariz_eslatma(message, user)


@dp.message(Command("admin"))
async def admin_buyruq(message: Message) -> None:
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Ruxsat yo'q.")
        return
    await message.answer("🔐 <b>Admin paneli</b>", reply_markup=admin_menyu(), parse_mode="HTML")


# ─────────────────────────────────────────────
# HANDLERLAR — BALANS
# ─────────────────────────────────────────────

@dp.message(F.text.contains("Balansim"))
async def balans_handler(message: Message) -> None:
    """Balans, VIP status va referal ma'lumotlari."""
    user = user_olish(message.from_user.id)
    if not user:
        await message.answer("❌ Avval /start bosing.")
        return

    vip_matn = "\n👑 <b>VIP foydalanuvchi!</b>" if vip_mi(user["olmos"]) else f"\n📈 VIP uchun: {VIP_CHEGARA - user['olmos']} olmos kerak"
    qariz_matn = f"\n⚠️ Qarz: <b>{user['qariz']} olmos</b>" if user["qariz"] > 0 else ""
    narx = sozlama_olish("konvertatsiya_narx")
    referallar = referal_soni(user["user_id"])

    await message.answer(
        f"💎 <b>Balansingiz: {user['olmos']} olmos</b>{qariz_matn}{vip_matn}\n\n"
        f"📌 1 konvertatsiya = <b>{narx} olmos</b>\n"
        f"👥 Taklif qilgan do'stlar: <b>{referallar} ta</b>\n"
        f"🔗 Referal kod: <code>{user['referal_kodi']}</code>",
        reply_markup=asosiy_menyu(user),
        parse_mode="HTML"
    )
    await qariz_eslatma(message, user)


# ─────────────────────────────────────────────
# HANDLERLAR — KUNLIK BONUS
# ─────────────────────────────────────────────

@dp.message(F.text == "🎁 Kunlik bonus")
async def kunlik_bonus_handler(message: Message) -> None:
    """Har kuni 1 marta +1 olmos bonus."""
    user = user_olish(message.from_user.id)

    if not kunlik_bonus_tekshir(user["user_id"]):
        # Ertangi vaqtni hisoblash
        ertaga = (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")
        await message.answer(
            f"⏰ Bugun bonusni allaqachon oldingiz!\n\n"
            f"🔄 Keyingi bonus: <b>{ertaga}</b>",
            reply_markup=asosiy_menyu(user),
            parse_mode="HTML"
        )
        return

    # Bonus berish
    yangi_olmos = olmos_yangilash(user["user_id"], KUNLIK_BONUS)
    kunlik_bonus_belgilash(user["user_id"])
    yangi_user = user_olish(user["user_id"])

    await message.answer(
        f"🎁 <b>Kunlik bonus olindi!</b>\n\n"
        f"💎 +{KUNLIK_BONUS} olmos\n"
        f"💎 Yangi balans: <b>{yangi_olmos} olmos</b>",
        reply_markup=asosiy_menyu(yangi_user),
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────
# HANDLERLAR — REFERAL
# ─────────────────────────────────────────────

@dp.message(F.text == "👥 Referal")
async def referal_handler(message: Message) -> None:
    """Referal havolasini ko'rsatadi."""
    user = user_olish(message.from_user.id)
    bot_info = await bot.get_me()
    bot_username = bot_info.username
    referallar = referal_soni(user["user_id"])

    havola = f"https://t.me/{bot_username}?start={user['referal_kodi']}"

    await message.answer(
        f"👥 <b>Referal tizimi</b>\n\n"
        f"🔗 Sizning havolangiz:\n<code>{havola}</code>\n\n"
        f"👤 Taklif qilgan do'stlar: <b>{referallar} ta</b>\n"
        f"💎 Har bir do'st uchun: <b>+{REFERAL_OLMOS} olmos</b>\n\n"
        "Do'stlaringizga havola yuboring — ular qo'shilganda olmos olasiz!",
        reply_markup=asosiy_menyu(user),
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────
# HANDLERLAR — SOVG'A YUBORISH
# ─────────────────────────────────────────────

@dp.message(F.text == "🎀 Sovg'a yuborish")
async def sovga_boshlash(message: Message, state: FSMContext) -> None:
    """Sovg'a yuborish jarayonini boshlaydi."""
    user = user_olish(message.from_user.id)
    if user["olmos"] < SOVGA_MIN:
        await message.answer(
            f"❌ Sovg'a yuborish uchun kamida {SOVGA_MIN} olmos kerak!\n"
            f"💎 Sizda: {user['olmos']} olmos",
            reply_markup=asosiy_menyu(user),
        )
        return
    await state.set_state(SovgaState.user_id)
    await message.answer(
        "🎀 Kimga sovg'a yuborasiz?\n\n"
        "Foydalanuvchi <b>Telegram ID</b> sini kiriting:",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML"
    )


@dp.message(SovgaState.user_id)
async def sovga_user_id(message: Message, state: FSMContext) -> None:
    try:
        kimga_id = int(message.text.strip())
        if kimga_id == message.from_user.id:
            await message.answer("❌ O'zingizga sovg'a yubora olmaysiz!")
            await state.clear()
            return
        kimga = user_olish(kimga_id)
        if not kimga:
            await message.answer("❌ Bu foydalanuvchi botda ro'yxatdan o'tmagan.")
            await state.clear()
            return
        await state.update_data(kimga_id=kimga_id, kimga_nom=kimga["full_name"])
        await state.set_state(SovgaState.miqdor)
        user = user_olish(message.from_user.id)
        await message.answer(
            f"👤 Qabul qiluvchi: <b>{kimga['full_name']}</b>\n"
            f"💎 Sizda: <b>{user['olmos']} olmos</b>\n\n"
            "Necha olmos yuborasiz?",
            parse_mode="HTML"
        )
    except ValueError:
        await message.answer("❌ Faqat raqam (Telegram ID) kiriting.")
        await state.clear()


@dp.message(SovgaState.miqdor)
async def sovga_miqdor(message: Message, state: FSMContext) -> None:
    try:
        miqdor = int(message.text.strip())
        if miqdor < SOVGA_MIN:
            await message.answer(f"❌ Minimal sovg'a: {SOVGA_MIN} olmos.")
            await state.clear()
            return
        data = await state.get_data()
        kimga_id  = data["kimga_id"]
        kimga_nom = data["kimga_nom"]
        await state.clear()

        muvaffaq = sovga_yuborish(message.from_user.id, kimga_id, miqdor)
        user = user_olish(message.from_user.id)

        if not muvaffaq:
            await message.answer(
                "❌ Yetarli olmos yo'q yoki xato yuz berdi.",
                reply_markup=asosiy_menyu(user),
            )
            return

        await message.answer(
            f"🎀 <b>Sovg'a yuborildi!</b>\n\n"
            f"👤 Kimga: <b>{kimga_nom}</b>\n"
            f"💎 Miqdor: <b>{miqdor} olmos</b>\n"
            f"💎 Qolgan balans: <b>{user['olmos'] - miqdor} olmos</b>",
            reply_markup=asosiy_menyu(user_olish(message.from_user.id)),
            parse_mode="HTML"
        )

        # Qabul qiluvchiga xabar
        kimdan_user = user_olish(message.from_user.id)
        try:
            await bot.send_message(
                kimga_id,
                f"🎀 <b>{kimdan_user['full_name']}</b> sizga "
                f"<b>{miqdor} olmos</b> sovg'a qildi!",
                parse_mode="HTML"
            )
        except Exception:
            pass

    except ValueError:
        await message.answer("❌ Faqat raqam kiriting.")
        await state.clear()


# ─────────────────────────────────────────────
# HANDLERLAR — TOP REYTING
# ─────────────────────────────────────────────

@dp.message(F.text == "🏆 Top reyting")
async def top_reyting_handler(message: Message) -> None:
    """Eng ko'p olmosli 10 foydalanuvchi."""
    top = top_foydalanuvchilar(10)
    user = user_olish(message.from_user.id)

    if not top:
        await message.answer("📭 Hozircha ma'lumot yo'q.", reply_markup=asosiy_menyu(user))
        return

    medallar = ["🥇", "🥈", "🥉"]
    qatorlar = ["🏆 <b>Top 10 foydalanuvchilar:</b>\n"]

    for i, (ism, username, olmos) in enumerate(top, 1):
        medal = medallar[i-1] if i <= 3 else f"{i}."
        vip = "👑" if vip_mi(olmos) else ""
        qatorlar.append(f"{medal} {vip}<b>{ism}</b> — {olmos} 💎")

    await message.answer(
        "\n".join(qatorlar),
        reply_markup=asosiy_menyu(user),
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────
# HANDLERLAR — KESHBEK
# ─────────────────────────────────────────────

@dp.message(F.text == "💰 Keshbek olish")
async def keshbek_boshlash(message: Message, state: FSMContext) -> None:
    await state.set_state(KeshbekState.kod)
    await message.answer(
        "💰 <b>Keshbek kodi kiriting:</b>\n\n"
        "HisobchiXuzbot'dan olgan 3 qatorli kodingizni yuboring.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML"
    )


@dp.message(KeshbekState.kod)
async def keshbek_kod_qabul(message: Message, state: FSMContext) -> None:
    kod = message.text.strip()
    user = user_olish(message.from_user.id)
    await state.clear()

    natija = keshbek_kod_tekshir(kod)
    if not natija:
        await message.answer(
            "❌ <b>Kod topilmadi yoki muddati o'tgan!</b>",
            reply_markup=asosiy_menyu(user),
            parse_mode="HTML"
        )
        return

    yangi_olmos = olmos_yangilash(message.from_user.id, KESHBEK_OLMOS)
    yangi_user  = user_olish(message.from_user.id)

    await message.answer(
        f"✅ <b>Keshbek qo'shildi! +{KESHBEK_OLMOS} olmos</b>\n"
        f"💎 Yangi balans: <b>{yangi_olmos} olmos</b>",
        reply_markup=asosiy_menyu(yangi_user),
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────
# HANDLERLAR — QARIZ
# ─────────────────────────────────────────────

@dp.message(F.text == "🏦 Qariz olish")
async def qariz_olish(message: Message) -> None:
    user = user_olish(message.from_user.id)
    if user["olmos"] > 0:
        await message.answer("💎 Balansingizda olmos bor!", reply_markup=asosiy_menyu(user))
        return
    if user["qariz"] >= 3:
        await message.answer(
            "❌ Qariz limiti (3 olmos) to'lgan!\nKeshbek kodi orqali to'lang.",
            reply_markup=asosiy_menyu(user),
        )
        return
    olmos_yangilash(message.from_user.id, QARIZ_MIQDORI)
    qariz_yangilash(message.from_user.id, QARIZ_MIQDORI)
    yangi_user = user_olish(message.from_user.id)
    await message.answer(
        f"🏦 <b>+{QARIZ_MIQDORI} olmos qariz olindi!</b>\n"
        f"💎 Balans: <b>{yangi_user['olmos']} olmos</b>\n"
        f"⚠️ Qarz: <b>{yangi_user['qariz']} olmos</b>",
        reply_markup=asosiy_menyu(yangi_user),
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────
# HANDLERLAR — FAYL YUBORISH
# ─────────────────────────────────────────────

@dp.message(F.text == "📁 Fayl yuborish")
async def fayl_yuborish_handler(message: Message) -> None:
    user = user_olish(message.from_user.id)
    narx = int(sozlama_olish("konvertatsiya_narx"))
    vip_matn = " (VIP ✨)" if vip_mi(user["olmos"]) else ""
    await message.answer(
        f"📁 Faylni yuboring{vip_matn}\n"
        f"💎 Narxi: <b>{narx} olmos</b> | Balansingiz: <b>{user['olmos']} olmos</b>",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML"
    )


@dp.message(F.document)
async def fayl_qabul(message: Message) -> None:
    """Faylni qabul qiladi, konvertatsiya qiladi, keyin o'chiradi."""
    user = user_olish(message.from_user.id)
    if not user:
        await message.answer("❌ Avval /start bosing.")
        return

    narx = int(sozlama_olish("konvertatsiya_narx"))

    # VIP foydalanuvchilarga chegirma (agar 80+ olmos bo'lsa)
    if vip_mi(user["olmos"]) and narx > 1:
        narx = max(1, narx - 1)

    if user["olmos"] < narx:
        if user["qariz"] < 3:
            qariz_yangilash(message.from_user.id, narx)
            await message.answer(
                f"⚠️ Balansingiz yetmadi. <b>{narx} olmos</b> qariz olindi.",
                parse_mode="HTML"
            )
        else:
            await message.answer(
                "❌ Balansingiz yetarli emas!",
                reply_markup=asosiy_menyu(user),
            )
            return

    fayl = message.document
    fayl_nomi = fayl.file_name or "fayl"
    await message.answer(f"⏳ <b>{fayl_nomi}</b> qayta ishlanmoqda...", parse_mode="HTML")

    try:
        fayl_info = await bot.get_file(fayl.file_id)
        yuklab_olish_yoli = f"/tmp/{fayl_nomi}"
        await bot.download_file(fayl_info.file_path, yuklab_olish_yoli)

        # ── KONVERTATSIYA LOGIKASI SHU YERDA ──
        await message.answer_document(
            document=fayl.file_id,
            caption=f"✅ <b>{fayl_nomi}</b> qayta ishlandi!",
            parse_mode="HTML"
        )

        # Faylni o'chirish
        if os.path.exists(yuklab_olish_yoli):
            os.remove(yuklab_olish_yoli)

        olmos_yangilash(message.from_user.id, -narx)
        konvertatsiya_yozish(message.from_user.id, fayl_nomi)

        if user["qariz"] > 0:
            qariz_tozalash(message.from_user.id)
            await message.answer("✅ Qarzingiz to'landi!")

        yangi_user = user_olish(message.from_user.id)
        await message.answer(
            f"💎 Qolgan balans: <b>{yangi_user['olmos']} olmos</b>",
            reply_markup=asosiy_menyu(yangi_user),
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Fayl xatosi: {e}")
        await message.answer("❌ Xato yuz berdi.", reply_markup=asosiy_menyu(user))


# ─────────────────────────────────────────────
# HANDLERLAR — TARIX VA YORDAM
# ─────────────────────────────────────────────

@dp.message(F.text == "📊 Tarix")
async def tarix_handler(message: Message) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        SELECT fayl_nomi, yaratilgan FROM konvertatsiyalar
        WHERE user_id = ? ORDER BY id DESC LIMIT 10
    """, (message.from_user.id,))
    rows = cur.fetchall()
    conn.close()
    user = user_olish(message.from_user.id)

    if not rows:
        await message.answer("📭 Hozircha konvertatsiya yo'q.", reply_markup=asosiy_menyu(user))
        return

    qatorlar = ["📊 <b>So'nggi konvertatsiyalar:</b>\n"]
    for i, (nom, vaqt) in enumerate(rows, 1):
        qatorlar.append(f"{i}. 📄 {nom}\n   🕐 {vaqt}")

    await message.answer("\n\n".join(qatorlar), reply_markup=asosiy_menyu(user), parse_mode="HTML")


@dp.message(F.text == "❓ Yordam")
async def yordam_handler(message: Message) -> None:
    user = user_olish(message.from_user.id)
    narx = sozlama_olish("konvertatsiya_narx")
    await message.answer(
        "❓ <b>FaylMasterBot v2.0 — Yordam</b>\n\n"
        f"💎 Yangi user: {BOSHLANGICH_OLMOS} olmos\n"
        f"📁 1 konvertatsiya: {narx} olmos\n"
        f"🎁 Kunlik bonus: +{KUNLIK_BONUS} olmos\n"
        f"👥 Referal: +{REFERAL_OLMOS} olmos/do'st\n"
        f"🎀 Sovg'a: do'stga olmos yuboring\n"
        f"👑 VIP: {VIP_CHEGARA}+ olmos → maxsus status\n"
        f"💰 Keshbek: HisobchiXuzbot kodi → +{KESHBEK_OLMOS} olmos\n"
        f"🏦 Qariz: balans 0 bo'lsa +{QARIZ_MIQDORI} olmos",
        reply_markup=asosiy_menyu(user),
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────
# ADMIN HANDLERLAR
# ─────────────────────────────────────────────

@dp.message(F.text == "👥 Statistika")
async def admin_stat(message: Message) -> None:
    if message.from_user.id != ADMIN_ID:
        return
    stat = admin_statistika()
    narx = sozlama_olish("konvertatsiya_narx")
    await message.answer(
        "📊 <b>Admin statistika</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{stat['foydalanuvchilar']}</b>\n"
        f"📁 Konvertatsiyalar: <b>{stat['konvertatsiyalar']}</b>\n"
        f"👑 VIP foydalanuvchilar: <b>{stat['viplar']}</b>\n"
        f"⚠️ Qarzdorlar: <b>{stat['qarzdorlar']}</b>\n"
        f"🎀 Jami sovg'alar: <b>{stat['sovgalar']}</b>\n"
        f"💎 Jami olmos: <b>{stat['jami_olmos']}</b>\n"
        f"💲 Konvertatsiya narxi: <b>{narx} olmos</b>",
        parse_mode="HTML"
    )


@dp.message(F.text == "💎 Balans tahrirlash")
async def admin_balans_boshlash(message: Message, state: FSMContext) -> None:
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminState.balans_user_id)
    await message.answer("👤 Foydalanuvchi ID sini kiriting:", reply_markup=ReplyKeyboardRemove())


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
            f"👤 {user['full_name']} — {user['olmos']} olmos\nYangi miqdor:"
        )
    except ValueError:
        await message.answer("❌ Faqat raqam.")
        await state.clear()


@dp.message(AdminState.balans_miqdor)
async def admin_balans_miqdor_handler(message: Message, state: FSMContext) -> None:
    try:
        yangi = int(message.text.strip())
        data = await state.get_data()
        muvaffaq = admin_balans_ozgartir(data["target_user_id"], yangi)
        await state.clear()
        if muvaffaq:
            await message.answer(f"✅ Balans yangilandi: {min(yangi, MAX_OLMOS)} olmos", reply_markup=admin_menyu())
        else:
            await message.answer("❌ Xato.", reply_markup=admin_menyu())
    except ValueError:
        await message.answer("❌ Faqat raqam.")
        await state.clear()


@dp.message(F.text == "💲 Narx o'zgartirish")
async def admin_narx_boshlash(message: Message, state: FSMContext) -> None:
    if message.from_user.id != ADMIN_ID:
        return
    joriy = sozlama_olish("konvertatsiya_narx")
    await state.set_state(AdminState.narx_yangi)
    await message.answer(f"💲 Hozirgi narx: {joriy} olmos\nYangi narx:", reply_markup=ReplyKeyboardRemove())


@dp.message(AdminState.narx_yangi)
async def admin_narx_yangilash(message: Message, state: FSMContext) -> None:
    try:
        yangi = int(message.text.strip())
        if yangi < 1:
            raise ValueError
        sozlama_yangilash("konvertatsiya_narx", str(yangi))
        await state.clear()
        await message.answer(f"✅ Narx yangilandi: {yangi} olmos", reply_markup=admin_menyu())
    except ValueError:
        await message.answer("❌ Musbat raqam kiriting.")
        await state.clear()


@dp.message(F.text == "📢 Hammaga xabar")
async def admin_xabar_boshlash(message: Message, state: FSMContext) -> None:
    """Admin — barcha foydalanuvchilarga xabar yuborish."""
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminState.xabar_matn)
    await message.answer("📢 Xabar matnini kiriting:", reply_markup=ReplyKeyboardRemove())


@dp.message(AdminState.xabar_matn)
async def admin_xabar_yuborish(message: Message, state: FSMContext) -> None:
    """Barcha foydalanuvchilarga xabar yuboradi."""
    matn = message.text.strip()
    await state.clear()
    userlar = barcha_userlar()
    yuborildi = 0
    for uid in userlar:
        try:
            await bot.send_message(uid, f"📢 <b>Admin xabari:</b>\n\n{matn}", parse_mode="HTML")
            yuborildi += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await message.answer(
        f"✅ Xabar yuborildi: {yuborildi}/{len(userlar)} foydalanuvchi",
        reply_markup=admin_menyu()
    )


@dp.message(F.text == "🔙 Orqaga")
async def admin_orqaga(message: Message) -> None:
    if message.from_user.id != ADMIN_ID:
        return
    user = user_olish(message.from_user.id)
    await message.answer("✅ Asosiy menyu", reply_markup=asosiy_menyu(user))


# ─────────────────────────────────────────────
# NOMA'LUM XABARLAR
# ─────────────────────────────────────────────

@dp.message()
async def notanish(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current:
        return
    user = user_olish(message.from_user.id)
    if not user:
        await message.answer("Boshlash uchun /start bosing.")
        return
    await message.answer("🤔 Tushunmadim. Menyudan foydalaning:", reply_markup=asosiy_menyu(user))


# ─────────────────────────────────────────────
# ASOSIY ISHGA TUSHIRISH
# ─────────────────────────────────────────────

async def main() -> None:
    db_init()
    logger.info("FaylMasterBot v2.0 ishga tushdi ✅")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
