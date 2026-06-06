"""
FaylMasteruzbot v3.0 — Aiogram v3 + SQLite3
Yangi: Vazifa tizimi, Streak, Badge, Profil, Feedback, Shikoyat,
       PDF/Word/Rasm konvertatsiya, OCR, Tarjima
"""

import asyncio
import logging
import os
import sqlite3
import random
import string
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
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

# ─────────────────────────────────────────────
# SOZLAMALAR
# ─────────────────────────────────────────────

API_TOKEN          = "8829983191:AAFYyNiSKHZRuZJxZW9sc3hzFB39eGT9OSY"
ADMIN_ID           = 8314283278
DB_PATH            = "faylmaster.db"

BOSHLANGICH_OLMOS  = 5
MAX_OLMOS          = 100
KONVERTATSIYA_NARX = 1
QARIZ_MIQDORI      = 1
KESHBEK_OLMOS      = 1
REFERAL_OLMOS      = 2
KUNLIK_BONUS       = 1
SOVGA_MIN          = 1
VIP_CHEGARA        = 50
VAZIFA_MUDDAT      = 12    # soat

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# FSM HOLATLARI
# ─────────────────────────────────────────────

class KeshbekState(StatesGroup):
    kod = State()

class SovgaState(StatesGroup):
    user_id = State()
    miqdor  = State()

class AdminState(StatesGroup):
    balans_user_id  = State()
    balans_miqdor   = State()
    narx_yangi      = State()
    xabar_matn      = State()
    vazifa_matn     = State()
    vazifa_olmos    = State()

class FeedbackState(StatesGroup):
    matn = State()

class ShikoyatState(StatesGroup):
    matn = State()

class TarjimaState(StatesGroup):
    matn = State()


# ─────────────────────────────────────────────
# MA'LUMOTLAR BAZASI
# ─────────────────────────────────────────────

def db_init() -> None:
    """Barcha jadvallarni yaratadi."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

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
            streak         INTEGER DEFAULT 0,
            oxirgi_fayl    TEXT    DEFAULT NULL,
            joined_at      TEXT    DEFAULT (datetime('now'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS keshbek_kodlar (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            kod         TEXT    UNIQUE NOT NULL,
            user_id     INTEGER NOT NULL,
            yaratilgan  TEXT    DEFAULT (datetime('now')),
            ishlatilgan INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS konvertatsiyalar (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            fayl_nomi  TEXT,
            tur        TEXT    DEFAULT 'oddiy',
            yaratilgan TEXT    DEFAULT (datetime('now'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sovgalar (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            kimdan     INTEGER NOT NULL,
            kimga      INTEGER NOT NULL,
            miqdor     INTEGER NOT NULL,
            yaratilgan TEXT    DEFAULT (datetime('now'))
        )
    """)

    # Vazifalar jadvali
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vazifalar (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            matn       TEXT    NOT NULL,
            olmos      INTEGER NOT NULL,
            muddat     TEXT    NOT NULL,
            faol       INTEGER DEFAULT 1,
            yaratilgan TEXT    DEFAULT (datetime('now'))
        )
    """)

    # Vazifa javoblari
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vazifa_javoblar (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            vazifa_id  INTEGER NOT NULL,
            user_id    INTEGER NOT NULL,
            holat      TEXT    DEFAULT 'kutilmoqda',
            yaratilgan TEXT    DEFAULT (datetime('now')),
            UNIQUE(vazifa_id, user_id)
        )
    """)

    # Yutuqlar (badges)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS yutuqlar (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            tur        TEXT    NOT NULL,
            nom        TEXT    NOT NULL,
            yaratilgan TEXT    DEFAULT (datetime('now'))
        )
    """)

    # Feedbacklar
    cur.execute("""
        CREATE TABLE IF NOT EXISTS feedbacklar (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            matn       TEXT    NOT NULL,
            yaratilgan TEXT    DEFAULT (datetime('now'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sozlamalar (
            kalit  TEXT PRIMARY KEY,
            qiymat TEXT
        )
    """)

    cur.execute("INSERT OR IGNORE INTO sozlamalar (kalit, qiymat) VALUES ('konvertatsiya_narx', '1')")
    conn.commit()
    conn.close()


# ── Foydalanuvchi funksiyalari ──

def referal_kod_yarat(user_id: int) -> str:
    kod = "REF" + "".join(random.choices(string.ascii_uppercase + string.digits, k=7))
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("UPDATE users SET referal_kodi = ? WHERE user_id = ?", (kod, user_id))
    conn.commit()
    conn.close()
    return kod


def user_register(user_id: int, username: str, full_name: str, referal_kimdan: int = None) -> bool:
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
    referal_kod_yarat(user_id)
    if referal_kimdan:
        olmos_yangilash(referal_kimdan, REFERAL_OLMOS)
    return True


def user_olish(user_id: int) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        SELECT user_id, username, full_name, olmos, qariz,
               referal_kodi, kunlik_bonus, streak, oxirgi_fayl
        FROM users WHERE user_id = ?
    """, (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {
            "user_id": row[0], "username": row[1], "full_name": row[2],
            "olmos": row[3], "qariz": row[4], "referal_kodi": row[5],
            "kunlik_bonus": row[6], "streak": row[7], "oxirgi_fayl": row[8]
        }
    return None


def user_referal_koddan_topish(kod: str) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT user_id, full_name FROM users WHERE referal_kodi = ?", (kod,))
    row = cur.fetchone()
    conn.close()
    return {"user_id": row[0], "full_name": row[1]} if row else None


def olmos_yangilash(user_id: int, miqdor: int) -> int:
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


def streak_yangilash(user_id: int) -> int:
    """Ketma-ket kunlik faollikni yangilaydi."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT streak, oxirgi_fayl FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    streak, oxirgi = row if row else (0, None)
    bugun = datetime.now().date()

    if oxirgi:
        try:
            oxirgi_d = datetime.strptime(oxirgi, "%Y-%m-%d").date()
            if bugun == oxirgi_d:
                conn.close()
                return streak
            elif bugun - oxirgi_d == timedelta(days=1):
                streak += 1
            else:
                streak = 1
        except Exception:
            streak = 1
    else:
        streak = 1

    cur.execute(
        "UPDATE users SET streak = ?, oxirgi_fayl = ? WHERE user_id = ?",
        (streak, bugun.strftime("%Y-%m-%d"), user_id)
    )
    conn.commit()
    conn.close()
    return streak


def kunlik_bonus_tekshir(user_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT kunlik_bonus FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row or not row[0]:
        return True
    try:
        oxirgi = datetime.strptime(row[0], "%Y-%m-%d")
        return datetime.now().date() > oxirgi.date()
    except Exception:
        return True


def kunlik_bonus_belgilash(user_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("UPDATE users SET kunlik_bonus = ? WHERE user_id = ?",
                (datetime.now().strftime("%Y-%m-%d"), user_id))
    conn.commit()
    conn.close()


def top_foydalanuvchilar(limit: int = 10) -> list:
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT full_name, username, olmos FROM users ORDER BY olmos DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows


def referal_soni(user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE referal_kimdan = ?", (user_id,))
    soni = cur.fetchone()[0]
    conn.close()
    return soni


def sovga_yuborish(kimdan: int, kimga: int, miqdor: int) -> bool:
    k1 = user_olish(kimdan)
    k2 = user_olish(kimga)
    if not k1 or not k2 or k1["olmos"] < miqdor or miqdor < SOVGA_MIN:
        return False
    olmos_yangilash(kimdan, -miqdor)
    olmos_yangilash(kimga,  +miqdor)
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("INSERT INTO sovgalar (kimdan, kimga, miqdor) VALUES (?, ?, ?)", (kimdan, kimga, miqdor))
    conn.commit()
    conn.close()
    return True


def keshbek_kod_tekshir(kod: str) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT id, user_id, yaratilgan, ishlatilgan FROM keshbek_kodlar WHERE kod = ?", (kod,))
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


def konvertatsiya_yozish(user_id: int, fayl_nomi: str, tur: str = "oddiy") -> None:
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("INSERT INTO konvertatsiyalar (user_id, fayl_nomi, tur) VALUES (?, ?, ?)",
                (user_id, fayl_nomi, tur))
    conn.commit()
    conn.close()


# ── Vazifa funksiyalari ──

def vazifa_qosh(matn: str, olmos: int) -> int:
    """Yangi vazifa qo'shadi. Vazifa ID qaytaradi."""
    muddat = (datetime.now() + timedelta(hours=VAZIFA_MUDDAT)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("INSERT INTO vazifalar (matn, olmos, muddat) VALUES (?, ?, ?)", (matn, olmos, muddat))
    vazifa_id = cur.lastrowid
    conn.commit()
    conn.close()
    return vazifa_id


def faol_vazifa_olish() -> dict | None:
    """Hozirgi faol va muddati o'tmagan vazifani qaytaradi."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        SELECT id, matn, olmos, muddat FROM vazifalar
        WHERE faol = 1 AND muddat > datetime('now')
        ORDER BY id DESC LIMIT 1
    """)
    row = cur.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "matn": row[1], "olmos": row[2], "muddat": row[3]}
    return None


def vazifa_javob_qosh(vazifa_id: int, user_id: int) -> bool:
    """Foydalanuvchi vazifani bajardi deb belgilaydi."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    try:
        cur.execute("""
            INSERT OR IGNORE INTO vazifa_javoblar (vazifa_id, user_id)
            VALUES (?, ?)
        """, (vazifa_id, user_id))
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.close()
        return False


def vazifa_javob_yangilash(javob_id: int, holat: str) -> dict | None:
    """Admin tomonidan javob holatini yangilaydi."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT vazifa_id, user_id FROM vazifa_javoblar WHERE id = ?", (javob_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    cur.execute("UPDATE vazifa_javoblar SET holat = ? WHERE id = ?", (holat, javob_id))
    conn.commit()
    conn.close()
    return {"vazifa_id": row[0], "user_id": row[1]}


def vazifa_olmos_berish(javob_id: int) -> tuple | None:
    """Tasdiqlangan vazifaga olmos beradi."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        SELECT vj.user_id, v.olmos, vj.vazifa_id
        FROM vazifa_javoblar vj
        JOIN vazifalar v ON v.id = vj.vazifa_id
        WHERE vj.id = ?
    """, (javob_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    user_id, olmos, vazifa_id = row
    yangi = olmos_yangilash(user_id, olmos)
    return (user_id, olmos, yangi)


# ── Badge/Yutuq funksiyalari ──

BADGE_TURLARI = {
    "birinchi_konvertatsiya": "🏅 Birinchi qadam",
    "10_konvertatsiya":       "🥉 Faol foydalanuvchi",
    "50_konvertatsiya":       "🥈 Ustoz",
    "vip":                    "👑 VIP",
    "streak_7":               "🔥 7 kunlik streak",
    "streak_30":              "💫 30 kunlik streak",
    "referal_5":              "🤝 Mashhur do'st",
}


def badge_berish(user_id: int, tur: str) -> bool:
    """Foydalanuvchiga badge beradi (agar allaqachon yo'q bo'lsa)."""
    if tur not in BADGE_TURLARI:
        return False
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT id FROM yutuqlar WHERE user_id = ? AND tur = ?", (user_id, tur))
    if cur.fetchone():
        conn.close()
        return False
    cur.execute("INSERT INTO yutuqlar (user_id, tur, nom) VALUES (?, ?, ?)",
                (user_id, tur, BADGE_TURLARI[tur]))
    conn.commit()
    conn.close()
    return True


def yutuqlar_olish(user_id: int) -> list:
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT nom, yaratilgan FROM yutuqlar WHERE user_id = ? ORDER BY id", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def konvertatsiya_soni(user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM konvertatsiyalar WHERE user_id = ?", (user_id,))
    soni = cur.fetchone()[0]
    conn.close()
    return soni


async def badge_tekshir(bot: Bot, user_id: int, extra: dict = None) -> None:
    """Foydalanuvchi holatiga qarab badge beradi."""
    user    = user_olish(user_id)
    soni    = konvertatsiya_soni(user_id)
    ref_son = referal_soni(user_id)
    streak  = user.get("streak", 0)

    yangi_badgelar = []

    if soni >= 1  and badge_berish(user_id, "birinchi_konvertatsiya"):
        yangi_badgelar.append(BADGE_TURLARI["birinchi_konvertatsiya"])
    if soni >= 10 and badge_berish(user_id, "10_konvertatsiya"):
        yangi_badgelar.append(BADGE_TURLARI["10_konvertatsiya"])
    if soni >= 50 and badge_berish(user_id, "50_konvertatsiya"):
        yangi_badgelar.append(BADGE_TURLARI["50_konvertatsiya"])
    if user["olmos"] >= VIP_CHEGARA and badge_berish(user_id, "vip"):
        yangi_badgelar.append(BADGE_TURLARI["vip"])
    if streak >= 7  and badge_berish(user_id, "streak_7"):
        yangi_badgelar.append(BADGE_TURLARI["streak_7"])
    if streak >= 30 and badge_berish(user_id, "streak_30"):
        yangi_badgelar.append(BADGE_TURLARI["streak_30"])
    if ref_son >= 5 and badge_berish(user_id, "referal_5"):
        yangi_badgelar.append(BADGE_TURLARI["referal_5"])

    for badge in yangi_badgelar:
        try:
            await bot.send_message(user_id, f"🏆 Yangi yutuq: <b>{badge}</b>!", parse_mode="HTML")
        except Exception:
            pass


# ── Feedback ──

def feedback_saqlash(user_id: int, matn: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("INSERT INTO feedbacklar (user_id, matn) VALUES (?, ?)", (user_id, matn))
    conn.commit()
    conn.close()


# ── Admin ──

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
    f = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM konvertatsiyalar")
    k = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users WHERE qariz > 0")
    q = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*) FROM users WHERE olmos >= {VIP_CHEGARA}")
    v = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(SUM(olmos), 0) FROM users")
    o = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM feedbacklar")
    fb = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM vazifalar WHERE faol = 1")
    vz = cur.fetchone()[0]
    conn.close()
    return {
        "foydalanuvchilar": f, "konvertatsiyalar": k,
        "qarzdorlar": q, "viplar": v, "jami_olmos": o,
        "feedbacklar": fb, "vazifalar": vz
    }


def barcha_userlar() -> list:
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


# ─────────────────────────────────────────────
# YORDAMCHI
# ─────────────────────────────────────────────

def vip_mi(olmos: int) -> bool:
    return olmos >= VIP_CHEGARA


def vazifa_tasdiqlash_klaviatura(javob_id: int) -> InlineKeyboardMarkup:
    """Admin uchun tasdiqlash/rad etish tugmalari."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"vazifa_tasdiq_{javob_id}"),
        InlineKeyboardButton(text="❌ Rad etish",  callback_data=f"vazifa_rad_{javob_id}"),
    ]])


def bajardim_klaviatura(vazifa_id: int) -> InlineKeyboardMarkup:
    """Foydalanuvchi uchun 'Bajardim' tugmasi."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Bajardim", callback_data=f"bajardim_{vazifa_id}"),
    ]])


# ─────────────────────────────────────────────
# KLAVIATURA MENYULAR
# ─────────────────────────────────────────────

def asosiy_menyu(user: dict) -> ReplyKeyboardMarkup:
    vip_belgi = "👑 " if vip_mi(user.get("olmos", 0)) else ""
    tugmalar = [
        [KeyboardButton(text="📁 Fayl yuborish")],
        [KeyboardButton(text=f"💎 {vip_belgi}Balansim"), KeyboardButton(text="💰 Keshbek olish")],
        [KeyboardButton(text="🎁 Kunlik bonus"),         KeyboardButton(text="👥 Referal")],
        [KeyboardButton(text="🎀 Sovg'a yuborish"),      KeyboardButton(text="🏆 Top reyting")],
        [KeyboardButton(text="📋 Vazifalar"),             KeyboardButton(text="👤 Profilim")],
        [KeyboardButton(text="🌐 Tarjima"),               KeyboardButton(text="💬 Feedback")],
        [KeyboardButton(text="📊 Tarix"),                 KeyboardButton(text="❓ Yordam")],
    ]
    if user.get("olmos", 0) == 0:
        tugmalar.append([KeyboardButton(text="🏦 Qariz olish")])
    return ReplyKeyboardMarkup(keyboard=tugmalar, resize_keyboard=True)


def admin_menyu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Statistika")],
            [KeyboardButton(text="💎 Balans tahrirlash"), KeyboardButton(text="💲 Narx o'zgartirish")],
            [KeyboardButton(text="📢 Hammaga xabar"),     KeyboardButton(text="📋 Vazifa qo'shish")],
            [KeyboardButton(text="🔙 Orqaga")],
        ],
        resize_keyboard=True,
    )


# ─────────────────────────────────────────────
# BOT VA DISPATCHER
# ─────────────────────────────────────────────

bot = Bot(token=API_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())


async def qariz_eslatma(message: Message, user: dict) -> None:
    if user.get("qariz", 0) > 0:
        await message.answer(
            f"⚠️ <b>Sizda {user['qariz']} olmos qarzdorlik bor!</b>",
            parse_mode="HTML"
        )


# ─────────────────────────────────────────────
# HANDLERLAR — START
# ─────────────────────────────────────────────

@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    u = message.from_user
    referal_kimdan = None
    args = message.text.split()
    if len(args) > 1:
        taklif = user_referal_koddan_topish(args[1].strip())
        if taklif and taklif["user_id"] != u.id:
            referal_kimdan = taklif["user_id"]

    yangi = user_register(u.id, u.username or "", u.full_name or "", referal_kimdan)
    user  = user_olish(u.id)

    if yangi:
        if referal_kimdan:
            try:
                await bot.send_message(
                    referal_kimdan,
                    f"🎉 <b>{u.full_name}</b> havolangiz orqali qo'shildi!\n💎 +{REFERAL_OLMOS} olmos!",
                    parse_mode="HTML"
                )
            except Exception:
                pass
        xabar = (
            f"👋 Salom, <b>{u.full_name}</b>!\n\n"
            f"🎁 Sizga <b>{BOSHLANGICH_OLMOS} olmos</b> sovg'a!\n"
            "📁 FaylMasterBot — fayllarni konvertatsiya qiluvchi bot."
        )
    else:
        vip_m = " 👑 VIP" if vip_mi(user["olmos"]) else ""
        xabar = f"👋 Qaytib keldingiz, <b>{u.full_name}</b>{vip_m}!"

    await message.answer(xabar, reply_markup=asosiy_menyu(user), parse_mode="HTML")
    await qariz_eslatma(message, user)


@dp.message(Command("admin"))
async def admin_buyruq(message: Message) -> None:
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Ruxsat yo'q.")
        return

    # Admin panelini ko'rsatish
    await message.answer("🔐 <b>Admin paneli</b>", reply_markup=admin_menyu(), parse_mode="HTML")

    # Barcha foydalanuvchilarni chiqarish
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        SELECT user_id, full_name, username, olmos, qariz, joined_at
        FROM users ORDER BY joined_at DESC
    """)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await message.answer("📭 Hozircha foydalanuvchi yo'q.")
        return

    # Har 10 ta userdan bir xabar (Telegram limit uchun)
    for i in range(0, len(rows), 10):
        qism = rows[i:i+10]
        qatorlar = [f"👥 <b>Foydalanuvchilar ({i+1}-{i+len(qism)}):</b>\n"]
        for user_id, full_name, username, olmos, qariz, joined in qism:
            vip_b    = "👑" if olmos >= VIP_CHEGARA else ""
            qariz_b  = f"⚠️{qariz}" if qariz > 0 else ""
            uname    = f"@{username}" if username else "—"
            qatorlar.append(
                f"{vip_b} <b>{full_name}</b> {qariz_b}\n"
                f"   🆔 <code>{user_id}</code>\n"
                f"   👤 {uname} | 💎 {olmos} olmos"
            )
        await message.answer("\n\n".join(qatorlar), parse_mode="HTML")
        await asyncio.sleep(0.3)


# ─────────────────────────────────────────────
# HANDLERLAR — PROFIL
# ─────────────────────────────────────────────

@dp.message(F.text == "👤 Profilim")
async def profil_handler(message: Message) -> None:
    user    = user_olish(message.from_user.id)
    soni    = konvertatsiya_soni(user["user_id"])
    ref_son = referal_soni(user["user_id"])
    yutuqlar = yutuqlar_olish(user["user_id"])
    vip_m   = "👑 VIP" if vip_mi(user["olmos"]) else "Oddiy"

    badge_matn = ""
    if yutuqlar:
        badge_matn = "\n\n🏆 <b>Yutuqlar:</b>\n" + "\n".join([f"• {y[0]}" for y in yutuqlar])

    await message.answer(
        f"👤 <b>Profil</b>\n\n"
        f"👤 Ism: <b>{user['full_name']}</b>\n"
        f"💎 Olmos: <b>{user['olmos']}</b>\n"
        f"⭐ Status: <b>{vip_m}</b>\n"
        f"📁 Konvertatsiyalar: <b>{soni}</b>\n"
        f"🔥 Streak: <b>{user['streak']} kun</b>\n"
        f"👥 Referallar: <b>{ref_son} ta</b>\n"
        f"🔗 Referal kod: <code>{user['referal_kodi']}</code>"
        f"{badge_matn}",
        reply_markup=asosiy_menyu(user),
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────
# HANDLERLAR — BALANS
# ─────────────────────────────────────────────

@dp.message(F.text.contains("Balansim"))
async def balans_handler(message: Message) -> None:
    user = user_olish(message.from_user.id)
    if not user:
        await message.answer("❌ Avval /start bosing.")
        return
    vip_m      = "\n👑 <b>VIP foydalanuvchi!</b>" if vip_mi(user["olmos"]) else f"\n📈 VIP uchun: {VIP_CHEGARA - user['olmos']} olmos kerak"
    qariz_m    = f"\n⚠️ Qarz: <b>{user['qariz']} olmos</b>" if user["qariz"] > 0 else ""
    narx       = sozlama_olish("konvertatsiya_narx")
    ref_son    = referal_soni(user["user_id"])
    await message.answer(
        f"💎 <b>Balans: {user['olmos']} olmos</b>{qariz_m}{vip_m}\n\n"
        f"📌 1 konvertatsiya = <b>{narx} olmos</b>\n"
        f"🔥 Streak: <b>{user['streak']} kun</b>\n"
        f"👥 Referallar: <b>{ref_son} ta</b>\n"
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
    user = user_olish(message.from_user.id)
    if not kunlik_bonus_tekshir(user["user_id"]):
        ertaga = (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")
        await message.answer(
            f"⏰ Bugun bonusni oldingiz!\n🔄 Keyingi bonus: <b>{ertaga}</b>",
            reply_markup=asosiy_menyu(user), parse_mode="HTML"
        )
        return

    # Streak bonusi
    streak   = streak_yangilash(user["user_id"])
    bonus    = KUNLIK_BONUS
    if streak >= 30:
        bonus = 3
    elif streak >= 7:
        bonus = 2

    yangi_olmos = olmos_yangilash(user["user_id"], bonus)
    kunlik_bonus_belgilash(user["user_id"])
    yangi_user  = user_olish(user["user_id"])

    streak_m = ""
    if streak >= 7:
        streak_m = f"\n🔥 <b>{streak} kunlik streak!</b> Bonus x{bonus}"

    await message.answer(
        f"🎁 <b>Kunlik bonus: +{bonus} olmos!</b>{streak_m}\n"
        f"💎 Yangi balans: <b>{yangi_olmos} olmos</b>",
        reply_markup=asosiy_menyu(yangi_user), parse_mode="HTML"
    )
    await badge_tekshir(bot, user["user_id"])


# ─────────────────────────────────────────────
# HANDLERLAR — REFERAL
# ─────────────────────────────────────────────

@dp.message(F.text == "👥 Referal")
async def referal_handler(message: Message) -> None:
    user     = user_olish(message.from_user.id)
    bot_info = await bot.get_me()
    havola   = f"https://t.me/{bot_info.username}?start={user['referal_kodi']}"
    ref_son  = referal_soni(user["user_id"])
    await message.answer(
        f"👥 <b>Referal tizimi</b>\n\n"
        f"🔗 Havolangiz:\n<code>{havola}</code>\n\n"
        f"👤 Taklif qilganlar: <b>{ref_son} ta</b>\n"
        f"💎 Har bir do'st: <b>+{REFERAL_OLMOS} olmos</b>",
        reply_markup=asosiy_menyu(user), parse_mode="HTML"
    )


# ─────────────────────────────────────────────
# HANDLERLAR — SOVG'A
# ─────────────────────────────────────────────

@dp.message(F.text == "🎀 Sovg'a yuborish")
async def sovga_boshlash(message: Message, state: FSMContext) -> None:
    user = user_olish(message.from_user.id)
    if user["olmos"] < SOVGA_MIN:
        await message.answer(f"❌ Kamida {SOVGA_MIN} olmos kerak!", reply_markup=asosiy_menyu(user))
        return
    await state.set_state(SovgaState.user_id)
    await message.answer("🎀 Kimga sovg'a? Telegram ID kiriting:", reply_markup=ReplyKeyboardRemove())


@dp.message(SovgaState.user_id)
async def sovga_user_id(message: Message, state: FSMContext) -> None:
    try:
        kimga_id = int(message.text.strip())
        if kimga_id == message.from_user.id:
            await message.answer("❌ O'zingizga yubora olmaysiz!")
            await state.clear()
            return
        kimga = user_olish(kimga_id)
        if not kimga:
            await message.answer("❌ Foydalanuvchi topilmadi.")
            await state.clear()
            return
        await state.update_data(kimga_id=kimga_id, kimga_nom=kimga["full_name"])
        await state.set_state(SovgaState.miqdor)
        user = user_olish(message.from_user.id)
        await message.answer(
            f"👤 Qabul qiluvchi: <b>{kimga['full_name']}</b>\n"
            f"💎 Sizda: <b>{user['olmos']} olmos</b>\n\nNecha olmos?",
            parse_mode="HTML"
        )
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting.")
        await state.clear()


@dp.message(SovgaState.miqdor)
async def sovga_miqdor(message: Message, state: FSMContext) -> None:
    try:
        miqdor = int(message.text.strip())
        data   = await state.get_data()
        kimga_id  = data["kimga_id"]
        kimga_nom = data["kimga_nom"]
        await state.clear()
        muvaffaq = sovga_yuborish(message.from_user.id, kimga_id, miqdor)
        user     = user_olish(message.from_user.id)
        if not muvaffaq:
            await message.answer("❌ Yetarli olmos yo'q!", reply_markup=asosiy_menyu(user))
            return
        await message.answer(
            f"🎀 <b>{kimga_nom}</b> ga <b>{miqdor} olmos</b> yuborildi!",
            reply_markup=asosiy_menyu(user_olish(message.from_user.id)), parse_mode="HTML"
        )
        kimdan_user = user_olish(message.from_user.id)
        try:
            await bot.send_message(kimga_id,
                f"🎀 <b>{kimdan_user['full_name']}</b> sizga <b>{miqdor} olmos</b> sovg'a qildi!",
                parse_mode="HTML")
        except Exception:
            pass
    except ValueError:
        await message.answer("❌ Faqat raqam.")
        await state.clear()


# ─────────────────────────────────────────────
# HANDLERLAR — TOP REYTING
# ─────────────────────────────────────────────

@dp.message(F.text == "🏆 Top reyting")
async def top_reyting_handler(message: Message) -> None:
    top  = top_foydalanuvchilar(10)
    user = user_olish(message.from_user.id)
    if not top:
        await message.answer("📭 Ma'lumot yo'q.", reply_markup=asosiy_menyu(user))
        return
    medallar = ["🥇", "🥈", "🥉"]
    qatorlar = ["🏆 <b>Top 10:</b>\n"]
    for i, (ism, username, olmos) in enumerate(top, 1):
        medal = medallar[i-1] if i <= 3 else f"{i}."
        vip   = "👑" if vip_mi(olmos) else ""
        qatorlar.append(f"{medal} {vip}<b>{ism}</b> — {olmos} 💎")
    await message.answer("\n".join(qatorlar), reply_markup=asosiy_menyu(user), parse_mode="HTML")


# ─────────────────────────────────────────────
# HANDLERLAR — VAZIFALAR
# ─────────────────────────────────────────────

@dp.message(F.text == "📋 Vazifalar")
async def vazifalar_handler(message: Message) -> None:
    """Faol vazifani ko'rsatadi."""
    user   = user_olish(message.from_user.id)
    vazifa = faol_vazifa_olish()

    if not vazifa:
        await message.answer(
            "📋 Hozircha faol vazifa yo'q.\nAdmin tez orada vazifa qo'shadi!",
            reply_markup=asosiy_menyu(user)
        )
        return

    muddat_dt = datetime.strptime(vazifa["muddat"], "%Y-%m-%d %H:%M:%S")
    qolgan    = muddat_dt - datetime.now()
    soat      = int(qolgan.total_seconds() // 3600)
    daqiqa    = int((qolgan.total_seconds() % 3600) // 60)

    await message.answer(
        f"📋 <b>Faol vazifa</b>\n\n"
        f"📝 {vazifa['matn']}\n\n"
        f"💎 Mukofot: <b>{vazifa['olmos']} olmos</b>\n"
        f"⏰ Qolgan vaqt: <b>{soat} soat {daqiqa} daqiqa</b>\n\n"
        "Vazifani bajarsangiz quyidagi tugmani bosing:",
        reply_markup=asosiy_menyu(user),
        parse_mode="HTML"
    )
    # Bajardim tugmasi
    await message.answer(
        "👇",
        reply_markup=bajardim_klaviatura(vazifa["id"])
    )


@dp.callback_query(F.data.startswith("bajardim_"))
async def bajardim_callback(callback: CallbackQuery) -> None:
    """Foydalanuvchi 'Bajardim' tugmasini bosdi."""
    vazifa_id = int(callback.data.split("_")[1])
    user_id   = callback.from_user.id
    user      = user_olish(user_id)

    vazifa = faol_vazifa_olish()
    if not vazifa or vazifa["id"] != vazifa_id:
        await callback.answer("❌ Vazifa muddati tugagan!", show_alert=True)
        return

    # Javobni bazaga yozish
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT id FROM vazifa_javoblar WHERE vazifa_id = ? AND user_id = ?", (vazifa_id, user_id))
    mavjud = cur.fetchone()
    if mavjud:
        conn.close()
        await callback.answer("✅ Siz allaqachon javob yuborgansiz!", show_alert=True)
        return
    cur.execute("INSERT INTO vazifa_javoblar (vazifa_id, user_id) VALUES (?, ?)", (vazifa_id, user_id))
    javob_id = cur.lastrowid
    conn.commit()
    conn.close()

    await callback.answer("✅ Javobingiz adminga yuborildi!", show_alert=True)
    await callback.message.answer(
        "⏳ Javobingiz admin tomonidan tekshirilmoqda...",
        reply_markup=asosiy_menyu(user)
    )

    # Adminga xabar
    try:
        await bot.send_message(
            ADMIN_ID,
            f"📋 <b>Yangi vazifa javobi!</b>\n\n"
            f"👤 Foydalanuvchi: <b>{user['full_name']}</b> (ID: {user_id})\n"
            f"📝 Vazifa: {vazifa['matn']}\n"
            f"💎 Mukofot: {vazifa['olmos']} olmos",
            reply_markup=vazifa_tasdiqlash_klaviatura(javob_id),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Admin xabar xatosi: {e}")


@dp.callback_query(F.data.startswith("vazifa_tasdiq_"))
async def vazifa_tasdiq_callback(callback: CallbackQuery) -> None:
    """Admin vazifani tasdiqladi."""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
        return

    javob_id = int(callback.data.split("_")[2])
    natija   = vazifa_javob_yangilash(javob_id, "tasdiqlandi")

    if not natija:
        await callback.answer("❌ Javob topilmadi!", show_alert=True)
        return

    olmos_natija = vazifa_olmos_berish(javob_id)
    if olmos_natija:
        user_id, olmos, yangi = olmos_natija
        try:
            await bot.send_message(
                user_id,
                f"✅ <b>Vazifa tasdiqlandi!</b>\n"
                f"💎 +{olmos} olmos hisoblandi!\n"
                f"💎 Yangi balans: <b>{yangi} olmos</b>",
                parse_mode="HTML"
            )
            await badge_tekshir(bot, user_id)
        except Exception:
            pass

    await callback.message.edit_text(
        callback.message.text + "\n\n✅ <b>TASDIQLANDI</b>",
        parse_mode="HTML"
    )
    await callback.answer("✅ Tasdiqlandi!", show_alert=True)


@dp.callback_query(F.data.startswith("vazifa_rad_"))
async def vazifa_rad_callback(callback: CallbackQuery) -> None:
    """Admin vazifani rad etdi."""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
        return

    javob_id = int(callback.data.split("_")[2])
    natija   = vazifa_javob_yangilash(javob_id, "rad etildi")

    if not natija:
        await callback.answer("❌ Javob topilmadi!", show_alert=True)
        return

    try:
        await bot.send_message(
            natija["user_id"],
            "❌ <b>Vazifa rad etildi.</b>\n"
            "Qayta urinib ko'ring yoki boshqa vazifani kuting.",
            parse_mode="HTML"
        )
    except Exception:
        pass

    await callback.message.edit_text(
        callback.message.text + "\n\n❌ <b>RAD ETILDI</b>",
        parse_mode="HTML"
    )
    await callback.answer("❌ Rad etildi!", show_alert=True)


# ─────────────────────────────────────────────
# HANDLERLAR — TARJIMA
# ─────────────────────────────────────────────

@dp.message(F.text == "🌐 Tarjima")
async def tarjima_boshlash(message: Message, state: FSMContext) -> None:
    user = user_olish(message.from_user.id)
    await state.set_state(TarjimaState.matn)
    await message.answer(
        "🌐 Tarjima qilmoqchi bo'lgan matnni yuboring:\n"
        "(Istalgan tildan o'zbek tiliga tarjima qilinadi)",
        reply_markup=ReplyKeyboardRemove()
    )


@dp.message(TarjimaState.matn)
async def tarjima_qilish(message: Message, state: FSMContext) -> None:
    """Matnni o'zbek tiliga tarjima qiladi."""
    matn = message.text.strip()
    user = user_olish(message.from_user.id)
    await state.clear()

    await message.answer("⏳ Tarjima qilinmoqda...")

    try:
        from deep_translator import GoogleTranslator
        tarjima = GoogleTranslator(source="auto", target="uz").translate(matn)
        await message.answer(
            f"🌐 <b>Tarjima natijasi:</b>\n\n{tarjima}",
            reply_markup=asosiy_menyu(user),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Tarjima xatosi: {e}")
        await message.answer(
            "❌ Tarjima xizmati hozir ishlamayapti.",
            reply_markup=asosiy_menyu(user)
        )


# ─────────────────────────────────────────────
# HANDLERLAR — FEEDBACK VA SHIKOYAT
# ─────────────────────────────────────────────

@dp.message(F.text == "💬 Feedback")
async def feedback_boshlash(message: Message, state: FSMContext) -> None:
    await state.set_state(FeedbackState.matn)
    await message.answer(
        "💬 Fikr-mulohazangizni yozing:\n(Bot haqida taklif, shikoyat yoki baho)",
        reply_markup=ReplyKeyboardRemove()
    )


@dp.message(FeedbackState.matn)
async def feedback_qabul(message: Message, state: FSMContext) -> None:
    user = user_olish(message.from_user.id)
    feedback_saqlash(user["user_id"], message.text.strip())
    await state.clear()
    try:
        await bot.send_message(
            ADMIN_ID,
            f"💬 <b>Yangi feedback!</b>\n\n"
            f"👤 {user['full_name']} (ID: {user['user_id']})\n\n"
            f"📝 {message.text.strip()}",
            parse_mode="HTML"
        )
    except Exception:
        pass
    await message.answer(
        "✅ Feedbackingiz qabul qilindi! Rahmat 🙏",
        reply_markup=asosiy_menyu(user)
    )


# ─────────────────────────────────────────────
# HANDLERLAR — KESHBEK
# ─────────────────────────────────────────────

@dp.message(F.text == "💰 Keshbek olish")
async def keshbek_boshlash(message: Message, state: FSMContext) -> None:
    await state.set_state(KeshbekState.kod)
    await message.answer(
        "💰 HisobchiXuzbot'dan olgan kodni kiriting:",
        reply_markup=ReplyKeyboardRemove()
    )


@dp.message(KeshbekState.kod)
async def keshbek_kod_qabul(message: Message, state: FSMContext) -> None:
    kod  = message.text.strip()
    user = user_olish(message.from_user.id)
    await state.clear()
    natija = keshbek_kod_tekshir(kod)
    if not natija:
        await message.answer("❌ Kod topilmadi yoki muddati o'tgan!", reply_markup=asosiy_menyu(user))
        return
    yangi_olmos = olmos_yangilash(message.from_user.id, KESHBEK_OLMOS)
    yangi_user  = user_olish(message.from_user.id)
    await message.answer(
        f"✅ Keshbek qo'shildi! +{KESHBEK_OLMOS} olmos\n💎 Balans: <b>{yangi_olmos} olmos</b>",
        reply_markup=asosiy_menyu(yangi_user), parse_mode="HTML"
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
        await message.answer("❌ Qariz limiti to'lgan!", reply_markup=asosiy_menyu(user))
        return
    olmos_yangilash(message.from_user.id, QARIZ_MIQDORI)
    qariz_yangilash(message.from_user.id, QARIZ_MIQDORI)
    yangi_user = user_olish(message.from_user.id)
    await message.answer(
        f"🏦 +{QARIZ_MIQDORI} olmos qariz olindi!\n"
        f"💎 Balans: <b>{yangi_user['olmos']}</b> | ⚠️ Qarz: <b>{yangi_user['qariz']}</b>",
        reply_markup=asosiy_menyu(yangi_user), parse_mode="HTML"
    )


# ─────────────────────────────────────────────
# HANDLERLAR — FAYL YUBORISH
# ─────────────────────────────────────────────

@dp.message(F.text == "📁 Fayl yuborish")
async def fayl_yuborish_handler(message: Message) -> None:
    user = user_olish(message.from_user.id)
    narx = int(sozlama_olish("konvertatsiya_narx"))
    vip_m = " (VIP ✨)" if vip_mi(user["olmos"]) else ""
    await message.answer(
        f"📁 Faylni yuboring{vip_m}\n"
        f"💎 Narxi: <b>{narx} olmos</b> | Balansingiz: <b>{user['olmos']} olmos</b>\n\n"
        "📌 Qo'llab-quvvatlanadigan formatlar:\n"
        "• PDF, DOCX, XLSX, JPG, PNG va boshqalar",
        reply_markup=ReplyKeyboardRemove(), parse_mode="HTML"
    )


@dp.message(F.document | F.photo)
async def fayl_qabul(message: Message) -> None:
    """Faylni qabul qiladi va qayta ishlaydi."""
    user = user_olish(message.from_user.id)
    if not user:
        await message.answer("❌ Avval /start bosing.")
        return

    narx = int(sozlama_olish("konvertatsiya_narx"))
    if vip_mi(user["olmos"]) and narx > 1:
        narx = max(1, narx - 1)

    if user["olmos"] < narx:
        if user["qariz"] < 3:
            qariz_yangilash(message.from_user.id, narx)
            await message.answer(f"⚠️ Balansingiz yetmadi. {narx} olmos qariz olindi.", parse_mode="HTML")
        else:
            await message.answer("❌ Balansingiz yetarli emas!", reply_markup=asosiy_menyu(user))
            return

    # Fayl ma'lumotlarini olish
    if message.document:
        fayl      = message.document
        fayl_nomi = fayl.file_name or "fayl"
        fayl_id   = fayl.file_id
    else:
        fayl      = message.photo[-1]
        fayl_nomi = "rasm.jpg"
        fayl_id   = fayl.file_id

    await message.answer(f"⏳ <b>{fayl_nomi}</b> qayta ishlanmoqda...", parse_mode="HTML")

    try:
        fayl_info        = await bot.get_file(fayl_id)
        yuklab_olish_yoli = f"/tmp/{fayl_nomi}"
        await bot.download_file(fayl_info.file_path, yuklab_olish_yoli)

        # ── KONVERTATSIYA LOGIKASI ──
        # PDF → Word, Word → PDF va boshqa konvertatsiyalar
        # Hozircha faylni qaytarib yuboramiz
        if message.document:
            await message.answer_document(
                document=fayl_id,
                caption=f"✅ <b>{fayl_nomi}</b> qayta ishlandi!",
                parse_mode="HTML"
            )
        else:
            await message.answer_photo(
                photo=fayl_id,
                caption="✅ Rasm qayta ishlandi!",
            )

        # Faylni o'chirish
        if os.path.exists(yuklab_olish_yoli):
            os.remove(yuklab_olish_yoli)

        # Olmos yechish
        olmos_yangilash(message.from_user.id, -narx)
        konvertatsiya_yozish(message.from_user.id, fayl_nomi)

        if user["qariz"] > 0:
            qariz_tozalash(message.from_user.id)
            await message.answer("✅ Qarzingiz to'landi!")

        yangi_user = user_olish(message.from_user.id)

        # Streak yangilash
        streak = streak_yangilash(message.from_user.id)
        streak_m = f"\n🔥 Streak: <b>{streak} kun</b>" if streak > 1 else ""

        await message.answer(
            f"💎 Qolgan balans: <b>{yangi_user['olmos']} olmos</b>{streak_m}",
            reply_markup=asosiy_menyu(yangi_user), parse_mode="HTML"
        )

        # Badge tekshirish
        await badge_tekshir(bot, message.from_user.id)

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
    """Har bir tugma haqida batafsil tushuntirish."""
    user = user_olish(message.from_user.id)
    narx = sozlama_olish("konvertatsiya_narx")

    # 1-xabar: Fayl yuborish va asosiy tushuntirish
    await message.answer(
        "❓ <b>FaylMasterBot — To'liq qo'llanma</b>\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n"
        "📁 <b>FAYL YUBORISH</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ «📁 Fayl yuborish» tugmasini bosing\n"
        "2️⃣ Istalgan faylingizni (rasm, hujjat va h.k.) botga yuboring\n"
        "3️⃣ Bot faylni qayta ishlab sizga qaytaradi\n"
        f"💡 Har bir fayl yuborish = <b>{narx} olmos</b> sarflaydi\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n"
        "💎 <b>OLMOS TIZIMI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• Botga birinchi kirsangiz: <b>{BOSHLANGICH_OLMOS} olmos</b> sovg'a\n"
        f"• Maksimal saqlash: <b>{MAX_OLMOS} olmos</b>\n"
        f"• Fayl yuborish narxi: <b>{narx} olmos</b>\n"
        f"• Olmos tugasa → <b>Qariz olish</b> mumkin (+{QARIZ_MIQDORI} olmos)",
        parse_mode="HTML"
    )

    # 2-xabar: Bonus va referal
    await message.answer(
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎁 <b>KUNLIK BONUS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "• Har kuni «🎁 Kunlik bonus» tugmasini bosing\n"
        f"• Oddiy: <b>+{KUNLIK_BONUS} olmos</b>\n"
        "• 7 kun ketma-ket: <b>+2 olmos</b> 🔥\n"
        "• 30 kun ketma-ket: <b>+3 olmos</b> 💫\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n"
        "👥 <b>REFERAL TIZIMI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ «👥 Referal» tugmasini bosing\n"
        "2️⃣ Shaxsiy havolangizni oling\n"
        "3️⃣ Do'stlaringizga yuboring\n"
        f"4️⃣ Do'st qo'shilganda: <b>+{REFERAL_OLMOS} olmos</b> olasiz\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎀 <b>SOVG'A YUBORISH</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ «🎀 Sovg'a yuborish» tugmasini bosing\n"
        "2️⃣ Do'stingizning Telegram ID sini kiriting\n"
        "3️⃣ Necha olmos yuborishni kiriting\n"
        "✅ Olmos darhol do'stingizga o'tadi",
        parse_mode="HTML"
    )

    # 3-xabar: Keshbek, VIP, Vazifalar
    await message.answer(
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💰 <b>KESHBEK OLISH</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ <b>HisobchiXuzbot</b> da xarajat kiriting\n"
        "2️⃣ Bot sizga maxsus kod beradi\n"
        "3️⃣ «💰 Keshbek olish» tugmasini bosing\n"
        "4️⃣ Kodni kiriting → balansga olmos qo'shiladi\n"
        "⚠️ Kod faqat <b>48 soat</b> amal qiladi!\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n"
        "👑 <b>VIP STATUS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• {VIP_CHEGARA} va undan ko'p olmos to'plasangiz — <b>VIP</b> bo'lasiz\n"
        "• VIP belgisi: 👑\n"
        "• Fayl yuborishda chegirma olasiz\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n"
        "📋 <b>VAZIFALAR</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ «📋 Vazifalar» tugmasini bosing\n"
        "2️⃣ Admin bergan vazifani o'qing\n"
        "3️⃣ Vazifani bajaring\n"
        "4️⃣ «✅ Bajardim» tugmasini bosing\n"
        "5️⃣ Admin tekshiradi → olmos hisoblaydi\n"
        f"⏰ Har bir vazifa <b>{VAZIFA_MUDDAT} soat</b> ichida bajarilishi kerak!",
        parse_mode="HTML"
    )

    # 4-xabar: Qolgan funksiyalar
    await message.answer(
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🌐 <b>TARJIMA</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ «🌐 Tarjima» tugmasini bosing\n"
        "2️⃣ Tarjima qilmoqchi bo'lgan matnni yuboring\n"
        "3️⃣ Bot istalgan tildan o'zbek tiliga tarjima qiladi\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n"
        "🏦 <b>QARIZ OLISH</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "• Balansiz 0 bo'lganda bu tugma chiqadi\n"
        f"• Bosing → <b>+{QARIZ_MIQDORI} olmos</b> qarz olasiz\n"
        "• Keyingi to'ldirishda qarz avtomatik to'lanadi\n"
        "• Maksimal qarz: <b>3 olmos</b>\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n"
        "🏆 <b>BOSHQA TUGMALAR</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "• «🏆 Top reyting» — eng ko'p olmosli 10 kishi\n"
        "• «👤 Profilim» — sizning to'liq statistikangiz\n"
        "• «📊 Tarix» — oxirgi 10 ta konvertatsiya\n"
        "• «💬 Feedback» — adminga taklif yoki shikoyat\n"
        "• «💎 Balansim» — joriy olmos va qarz holati",
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
        f"👑 VIP: <b>{stat['viplar']}</b>\n"
        f"⚠️ Qarzdorlar: <b>{stat['qarzdorlar']}</b>\n"
        f"💬 Feedbacklar: <b>{stat['feedbacklar']}</b>\n"
        f"📋 Faol vazifalar: <b>{stat['vazifalar']}</b>\n"
        f"💎 Jami olmos: <b>{stat['jami_olmos']}</b>\n"
        f"💲 Narx: <b>{narx} olmos</b>",
        parse_mode="HTML"
    )


@dp.message(F.text == "📋 Vazifa qo'shish")
async def admin_vazifa_boshlash(message: Message, state: FSMContext) -> None:
    """Admin yangi vazifa qo'shadi."""
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminState.vazifa_matn)
    await message.answer(
        "📋 Vazifa matnini kiriting:\n(Foydalanuvchilar nima qilishi kerak?)",
        reply_markup=ReplyKeyboardRemove()
    )


@dp.message(AdminState.vazifa_matn)
async def admin_vazifa_matn(message: Message, state: FSMContext) -> None:
    await state.update_data(vazifa_matn=message.text.strip())
    await state.set_state(AdminState.vazifa_olmos)
    await message.answer("💎 Vazifa uchun necha olmos berasiz?")


@dp.message(AdminState.vazifa_olmos)
async def admin_vazifa_olmos(message: Message, state: FSMContext) -> None:
    try:
        olmos = int(message.text.strip())
        if olmos < 1:
            raise ValueError
        data      = await state.get_data()
        vazifa_id = vazifa_qosh(data["vazifa_matn"], olmos)
        await state.clear()

        # Barcha userlarga vazifani yuborish
        userlar = barcha_userlar()
        await message.answer(
            f"✅ Vazifa qo'shildi! (ID: {vazifa_id})\n"
            f"💎 Mukofot: {olmos} olmos\n"
            f"⏰ Muddat: {VAZIFA_MUDDAT} soat\n\n"
            f"📢 {len(userlar)} ta foydalanuvchiga yuborilmoqda...",
            reply_markup=admin_menyu()
        )

        # Barcha userlarga yuborish
        yuborildi = 0
        for uid in userlar:
            try:
                await bot.send_message(
                    uid,
                    f"📋 <b>Yangi vazifa!</b>\n\n"
                    f"📝 {data['vazifa_matn']}\n\n"
                    f"💎 Mukofot: <b>{olmos} olmos</b>\n"
                    f"⏰ Muddat: <b>{VAZIFA_MUDDAT} soat</b>",
                    reply_markup=bajardim_klaviatura(vazifa_id),
                    parse_mode="HTML"
                )
                yuborildi += 1
                await asyncio.sleep(0.05)
            except Exception:
                pass

        await message.answer(f"✅ Yuborildi: {yuborildi}/{len(userlar)}", reply_markup=admin_menyu())

    except ValueError:
        await message.answer("❌ Musbat raqam kiriting.")
        await state.clear()


@dp.message(F.text == "💎 Balans tahrirlash")
async def admin_balans_boshlash(message: Message, state: FSMContext) -> None:
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminState.balans_user_id)
    await message.answer("👤 Foydalanuvchi ID:", reply_markup=ReplyKeyboardRemove())


@dp.message(AdminState.balans_user_id)
async def admin_balans_id(message: Message, state: FSMContext) -> None:
    try:
        user_id = int(message.text.strip())
        user    = user_olish(user_id)
        if not user:
            await message.answer("❌ Topilmadi.")
            await state.clear()
            return
        await state.update_data(target_user_id=user_id)
        await state.set_state(AdminState.balans_miqdor)
        await message.answer(f"👤 {user['full_name']} — {user['olmos']} olmos\nYangi miqdor:")
    except ValueError:
        await message.answer("❌ Faqat raqam.")
        await state.clear()


@dp.message(AdminState.balans_miqdor)
async def admin_balans_miqdor_handler(message: Message, state: FSMContext) -> None:
    try:
        yangi = int(message.text.strip())
        data  = await state.get_data()
        ok    = admin_balans_ozgartir(data["target_user_id"], yangi)
        await state.clear()
        if ok:
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
        await message.answer("❌ Musbat raqam.")
        await state.clear()


@dp.message(F.text == "📢 Hammaga xabar")
async def admin_xabar_boshlash(message: Message, state: FSMContext) -> None:
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminState.xabar_matn)
    await message.answer("📢 Xabar matnini kiriting:", reply_markup=ReplyKeyboardRemove())


@dp.message(AdminState.xabar_matn)
async def admin_xabar_yuborish(message: Message, state: FSMContext) -> None:
    matn    = message.text.strip()
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
    await message.answer(f"✅ Yuborildi: {yuborildi}/{len(userlar)}", reply_markup=admin_menyu())


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
    await message.answer("🤔 Tushunmadim.", reply_markup=asosiy_menyu(user))


# ─────────────────────────────────────────────
# ASOSIY ISHGA TUSHIRISH
# ─────────────────────────────────────────────

async def main() -> None:
    db_init()
    logger.info("FaylMasterBot v3.0 ishga tushdi ✅")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
