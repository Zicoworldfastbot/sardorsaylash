O'quvchilar Kengashi saylovi: Telegram bot + Mini App serveri (bitta fayl).
 
Nima qiladi:
  1. /start bosilganda "Ariza topshirish" tugmasini chiqaradi (Mini App ochadi).
  2. index.html ni internetga chiqaradi (Mini App shu).
  3. Mini App yuborgan arizani tekshiradi, Supabase bazasiga saqlaydi
     va adminga (ADMIN_ID) imzo rasmi + to'liq arizani yuboradi.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import time
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import parse_qsl
 
import httpx
from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BufferedInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)
from aiohttp import web
 
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("saylov")
 
# ----------------------------------------------------------------- SOZLAMALAR
BOT_TOKEN = os.environ["BOT_TOKEN"].strip()
SUPABASE_URL = os.environ["SUPABASE_URL"].strip().rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_KEY"].strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "1590570666"))
PORT = int(os.getenv("PORT", "8080"))
 
_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip().rstrip("/") or (
    f"https://{_domain}" if _domain else ""
)
 
DIRECTIONS = {
    "leader": "Kelajak liderligi",
    "education": "Ta'lim koordinatori",
    "culture": "Madaniyat koordinatori",
    "it": "IT va sun'iy intellekt koordinatori",
    "sport": "Sport koordinatori",
    "eco": "Ekologiya koordinatori",
    "media": "Media koordinatori",
    "social": "Ijtimoiy tashabbuslar koordinatori",
}
 
# ------------------------------------------------------------- TEKSHIRUVLAR
WORD_RE = re.compile(r"[^\W\d_](?:[^\W\d_]|['‘’ʻʼ`´-])+")
PHONE_RE = re.compile(r"\+998\d{9}")
CONTACT_RE = re.compile(r"(@[A-Za-z0-9_]{5,32}|[^@\s]+@[^@\s]+\.[^@\s]{2,})")
 
 
def check_name(raw: str):
    """To'liq Familiya + Ism bo'lsa, tozalangan nomni qaytaradi, aks holda None."""
    s = " ".join(str(raw).split())
    if not s or re.search(r"[.,\d_]", s):
        return None
    parts = s.split(" ")
    if not 2 <= len(parts) <= 4:
        return None
    for p in parts:
        if not WORD_RE.fullmatch(p):
            return None
        if sum(ch.isalpha() for ch in p) < 2:
            return None
    return " ".join(
        "-".join(seg[:1].upper() + seg[1:].lower() for seg in w.split("-"))
        for w in parts
    )
 
 
def verify_init_data(init_data: str):
    """Telegram initData haqiqiyligini tekshiradi. To'g'ri bo'lsa user dict qaytaradi."""
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        received = pairs.pop("hash", None)
        if not received:
            return None
        check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, received):
            return None
        if time.time() - int(pairs.get("auth_date", "0")) > 86400:
            return None
        user = json.loads(pairs["user"])
        return user if isinstance(user, dict) and "id" in user else None
    except Exception:
        return None
 
 
# ------------------------------------------------------------------ SUPABASE
def sb_headers(extra=None):
    h = {"apikey": SUPABASE_KEY, "Content-Type": "application/json"}
    if SUPABASE_KEY.startswith("eyJ"):  # eski service_role (JWT) kalit
        h["Authorization"] = f"Bearer {SUPABASE_KEY}"
    if extra:
        h.update(extra)
    return h
 
 
async def sb(method: str, path: str, **kw):
    headers = sb_headers(kw.pop("headers", None))
    async with httpx.AsyncClient(timeout=25) as client:
        return await client.request(
            method, f"{SUPABASE_URL}/rest/v1/{path}", headers=headers, **kw
        )
 
 
# --------------------------------------------------------------------- BOT
router = Router()
 
 
@router.message(CommandStart())
async def cmd_start(m: Message):
    if not WEBAPP_URL:
        await m.answer("⚠️ Bot hali to'liq sozlanmagan (WEBAPP_URL yo'q). Admin bilan bog'laning.")
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Ariza topshirish", web_app=WebAppInfo(url=WEBAPP_URL))]
        ]
    )
    await m.answer(
        "👋 <b>Assalomu alaykum!</b>\n\n"
        "🏫 Rishton tumani 30-umumiy o'rta ta'lim maktabi <b>O'quvchilar Kengashi</b> "
        "saylovida ishtirok etish uchun ariza topshiring.\n\n"
        "Quyidagi tugmani bosing 👇 va barcha savollarga javob bering. "
        "Oxirida imzo qo'yasiz.\n\n"
        "ℹ️ Mas'ul: maktab maslahatchisi F. Rahimjonov.",
        reply_markup=kb,
    )
 
 
@router.message(Command("stats"))
async def cmd_stats(m: Message):
    if m.from_user.id != ADMIN_ID:
        return
    r = await sb(
        "GET",
        "applications?select=grade,full_name,direction&order=grade.asc,created_at.asc",
    )
    if r.status_code != 200:
        await m.answer(f"Bazadan o'qib bo'lmadi: {r.status_code}")
        return
    rows = r.json()
    if not rows:
        await m.answer("Hozircha ariza yo'q.")
        return
    lines = [f"📊 <b>Jami arizalar: {len(rows)}</b>"]
    for g in range(5, 12):
        items = [x for x in rows if x["grade"] == g]
        lines.append(f"\n<b>{g}-sinf</b>: {len(items)} ta")
        for x in items:
            lines.append(f"  • {escape(x['full_name'])} — {escape(x['direction'])}")
    text, chunk = "", ""
    for line in lines:
        if len(chunk) + len(line) > 3800:
            await m.answer(chunk)
            chunk = ""
        chunk += line + "\n"
    if chunk:
        await m.answer(chunk)
 
 
# ----------------------------------------------------------------- MINI APP
def bad(msg: str, status: int = 400):
    return web.json_response({"ok": False, "error": msg}, status=status)
 
 
def build_text(row: dict) -> str:
    L = [
        "O'QUVCHILAR KENGASHI SAYLOVI — ARIZA",
        "=" * 40,
        f"Ariza raqami: {row.get('id', '-')}",
        f"Saylov bosqichi: Maktab bosqichi",
        f"F.I.Sh.: {row['full_name']}",
        f"Sinf: {row['grade']}-sinf",
        f"Yo'nalish: {row['direction']}",
        f"Aymoq: {row['region']}",
        f"Muassasa: {row['institution']}",
        f"Tug'ilgan sana: {row['birth_date']}",
        f"Telefon: {row['phone']}",
        f"Telegram/Email: {row['contact']}",
        f"Telegram akkaunt: id={row['telegram_id']}, username=@{row['telegram_username'] or '-'}",
        f"Topshirilgan vaqt (server): {datetime.now():%d.%m.%Y %H:%M}",
        "",
        "SAVOLLAR VA JAVOBLAR",
        "=" * 40,
    ]
    for i, a in enumerate(row["answers"], 1):
        L += [f"{i}. [{a['section']}] {a['q']}", a["a"], ""]
    L.append("Nomzod majburiyatlari bilan tanishdi va rozi bo'ldi. Imzo — alohida rasmda.")
    return "\n".join(L)
 
 
async def notify_admin(bot: Bot, row: dict, sig_bytes: bytes) -> bool:
    uname = f"@{escape(row['telegram_username'])}" if row["telegram_username"] else "yo'q"
    caption = (
        f"🆕 <b>Yangi ariza #{row.get('id', '')}</b>\n\n"
        f"👤 <b>{escape(row['full_name'])}</b>\n"
        f"🏫 {row['grade']}-sinf\n"
        f"🎯 {escape(row['direction'])}\n"
        f"📞 {escape(row['phone'])}\n"
        f"✉️ {escape(row['contact'])}\n"
        f"💬 Telegram: {uname} (id: <code>{row['telegram_id']}</code>)\n\n"
        f"✍️ Imzo pastda 👇"
    )
    try:
        await bot.send_photo(ADMIN_ID, BufferedInputFile(sig_bytes, "imzo.png"), caption=caption)
        safe = re.sub(r"\W+", "_", row["full_name"]) or "ariza"
        await bot.send_document(
            ADMIN_ID,
            BufferedInputFile(build_text(row).encode("utf-8"), f"ariza_{row['grade']}_{safe}.txt"),
            caption="📄 To'liq ariza (barcha javoblar)",
        )
        return True
    except Exception:
        log.exception("Adminga yuborib bo'lmadi. Admin botga /start bosganmi?")
        return False
 
 
async def api_submit(request: web.Request):
    bot: Bot = request.app["bot"]
    try:
        body = await request.json()
    except Exception:
        return bad("So'rov noto'g'ri.")
 
    user = verify_init_data(str(body.get("initData", "")))
    if not user:
        return bad("Ilovani Telegram bot orqali oching (/start bosing).", 403)
 
    d = body.get("data")
    if not isinstance(d, dict):
        return bad("Ma'lumotlar noto'g'ri.")
 
    grade = d.get("cls")
    if not isinstance(grade, int) or not 5 <= grade <= 11:
        return bad("Sinf noto'g'ri tanlangan.")
 
    name = check_name(d.get("fullName", ""))
    if not name:
        return bad("Ism-familiyani to'liq va qisqartirmasdan yozing (masalan: Qazaqbayev Jamshid).")
 
    dir_id = d.get("direction")
    if dir_id not in DIRECTIONS:
        return bad("Yo'nalish noto'g'ri tanlangan.")
 
    region = str(d.get("region", "")).strip()[:200]
    institution = str(d.get("institution", "")).strip()[:200]
    if len(region) < 3 or len(institution) < 3:
        return bad("Aymoq va muassasa nomini yozing.")
 
    try:
        birth = datetime.strptime(str(d.get("birth", "")), "%Y-%m-%d")
        if not 2005 <= birth.year <= 2017:
            raise ValueError
    except ValueError:
        return bad("Tug'ilgan sana noto'g'ri.")
 
    phone = str(d.get("phone", "")).strip()
    if not PHONE_RE.fullmatch(phone):
        return bad("Telefon raqami noto'g'ri.")
 
    contact = str(d.get("contact", "")).strip()[:100]
    if not CONTACT_RE.fullmatch(contact):
        return bad("Telegram username yoki email noto'g'ri.")
 
    if d.get("agree") is not True:
        return bad("Majburiyatlarga rozilik kerak.")
 
    answers = []
    counts = {}
    for section, key in (("Umumiy savol", "general"), ("Yo'nalish savoli", "special")):
        items = d.get(key) or []
        if not isinstance(items, list) or len(items) > 20:
            return bad("Javoblar noto'g'ri.")
        counts[key] = len(items)
        for it in items:
            if not isinstance(it, dict):
                return bad("Javoblar noto'g'ri.")
            q = str(it.get("q", "")).strip()[:300]
            a = str(it.get("a", "")).strip()
            if len(a) < 10 or len(a) > 1500:
                return bad("Har bir javob kamida 10 ta belgidan iborat bo'lishi kerak.")
            answers.append({"section": section, "q": q, "a": a})
    if counts["general"] != 10 or counts["special"] != (0 if dir_id == "leader" else 4):
        return bad("Savollar soni to'liq emas.")
 
    sig = str(d.get("signature", ""))
    if not sig.startswith("data:image/png;base64,") or len(sig) > 600_000:
        return bad("Imzo noto'g'ri.")
    try:
        sig_bytes = base64.b64decode(sig.split(",", 1)[1])
    except Exception:
        return bad("Imzo noto'g'ri.")
 
    row = {
        "telegram_id": int(user["id"]),
        "telegram_username": user.get("username"),
        "grade": grade,
        "full_name": name,
        "direction": DIRECTIONS[dir_id],
        "region": region,
        "institution": institution,
        "birth_date": birth.strftime("%Y-%m-%d"),
        "phone": phone,
        "contact": contact,
        "answers": answers,
        "signature": sig,
        "agreed": True,
    }
 
    try:
        r = await sb("POST", "applications", json=row, headers={"Prefer": "return=representation"})
    except Exception:
        log.exception("Supabase bilan aloqa yo'q")
        return bad("Server bazaga ulana olmadi. Birozdan keyin qayta urinib ko'ring.", 502)
 
    if r.status_code == 409:
        return bad("Siz allaqachon ariza topshirgansiz. Har bir o'quvchi faqat bitta ariza topshiradi.")
    if r.status_code not in (200, 201):
        log.error("Supabase xato %s: %s", r.status_code, r.text[:500])
        return bad("Arizani saqlashda xatolik. Keyinroq urinib ko'ring.", 500)
 
    try:
        row["id"] = r.json()[0]["id"]
    except Exception:
        row["id"] = "-"
 
    admin_ok = await notify_admin(bot, row, sig_bytes)
 
    try:
        await bot.send_message(
            row["telegram_id"],
            "✅ <b>Arizangiz qabul qilindi!</b>\n\n"
            f"👤 {escape(name)}\n🏫 {grade}-sinf\n🎯 {escape(DIRECTIONS[dir_id])}\n\n"
            "Natijalar haqida maktab maslahatchisi xabar beradi. Omad! 🍀",
        )
    except Exception:
        log.warning("O'quvchiga tasdiq xabari yuborilmadi")
 
    return web.json_response({"ok": True, "admin_notified": admin_ok})
 
 
async def index(request: web.Request):
    return web.FileResponse(
        Path(__file__).with_name("index.html"), headers={"Cache-Control": "no-store"}
    )
 
 
async def health(request: web.Request):
    return web.Response(text="ok")
 
 
# -------------------------------------------------------------------- MAIN
async def main():
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
 
    app = web.Application(client_max_size=2 * 1024 * 1024)
    app["bot"] = bot
    app.router.add_get("/", index)
    app.router.add_get("/health", health)
    app.router.add_post("/api/submit", api_submit)
 
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    log.info("Veb-server %s portda ishga tushdi. WEBAPP_URL=%s", PORT, WEBAPP_URL or "(yo'q)")
 
    await bot.delete_webhook(drop_pending_updates=True)
    if WEBAPP_URL:
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(text="Ariza topshirish", web_app=WebAppInfo(url=WEBAPP_URL))
            )
        except Exception:
            log.exception("Menyu tugmasini o'rnatib bo'lmadi")
 
    await dp.start_polling(bot, allowed_updates=["message"])
 
 
if __name__ == "__main__":
    asyncio.run(main())