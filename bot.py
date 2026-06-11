

import os, sqlite3, asyncio, random, string, zipfile, shutil
from datetime import datetime, timedelta
from urllib.parse import urlparse, urljoin

import aiohttp, aiofiles
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, FSInputFile
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from bs4 import BeautifulSoup

BOT_TOKEN = "8978305202:AAFikKlv2mXQeXWEfQ7P7trsRsklBszonQg"
ADMIN_ID = 6406769029
DB_FILE = "database.db"
DOWNLOAD_DIR = "downloads"

class Database:
    def __init__(self, db_file):
        self.db_file = db_file
        self.init_db()
    def get_conn(self):
        return sqlite3.connect(self.db_file, check_same_thread=False)
    def init_db(self):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
            join_date TEXT, credits INTEGER DEFAULT 0, total_used_credits INTEGER DEFAULT 0,
            total_generated_zips INTEGER DEFAULT 0, referral_code TEXT UNIQUE,
            referred_by INTEGER DEFAULT 0, referral_count INTEGER DEFAULT 0,
            premium_status INTEGER DEFAULT 0, premium_plan TEXT,
            premium_expire_date TEXT, banned_status INTEGER DEFAULT 0)""")
        c.execute("""CREATE TABLE IF NOT EXISTS zip_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, url TEXT,
            zip_file_name TEXT, total_files INTEGER, created_time TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT, channel_name TEXT, channel_link TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, price TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS bots_marketplace (
            id INTEGER PRIMARY KEY AUTOINCREMENT, bot_username TEXT,
            bot_link TEXT, description TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS api_marketplace (
            id INTEGER PRIMARY KEY AUTOINCREMENT, api_title TEXT, api_description TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            group_link TEXT, reason TEXT, status TEXT DEFAULT 'pending')""")
        c.execute("""CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1), new_user_credit INTEGER DEFAULT 5,
            referral_user_credit INTEGER DEFAULT 2, referral_owner_credit INTEGER DEFAULT 1,
            zip_cost INTEGER DEFAULT 1, maintenance_mode INTEGER DEFAULT 0,
            maintenance_message TEXT DEFAULT 'Bot is under maintenance. Please try again later.')""")
        c.execute("SELECT * FROM settings WHERE id = 1")
        if not c.fetchone(): c.execute("INSERT INTO settings (id) VALUES (1)")
        conn.commit(); conn.close()

    def get_user(self, user_id):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        r = c.fetchone(); conn.close(); return r
    def add_user(self, user_id, username, first_name):
        conn = self.get_conn(); c = conn.cursor()
        jd = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rc = "RAI" + str(user_id) + ''.join(random.choices(string.ascii_uppercase, k=4))
        s = self.get_settings()
        c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, join_date, credits, referral_code) VALUES (?, ?, ?, ?, ?, ?)",
                  (user_id, username, first_name, jd, s['new_user_credit'], rc))
        conn.commit(); conn.close()
    def get_settings(self):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM settings WHERE id = 1")
        r = c.fetchone(); conn.close()
        if r: return {'new_user_credit': r[1], 'referral_user_credit': r[2], 'referral_owner_credit': r[3], 'zip_cost': r[4], 'maintenance_mode': r[5], 'maintenance_message': r[6]}
        return {'new_user_credit': 5, 'referral_user_credit': 2, 'referral_owner_credit': 1, 'zip_cost': 1, 'maintenance_mode': 0, 'maintenance_message': 'Bot is under maintenance. Please try again later.'}
    def update_settings(self, **kwargs):
        conn = self.get_conn(); c = conn.cursor()
        for k, v in kwargs.items(): c.execute(f"UPDATE settings SET {k} = ? WHERE id = 1", (v,))
        conn.commit(); conn.close()
    def add_credits(self, user_id, amount):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (amount, user_id))
        conn.commit(); conn.close()
    def remove_credits(self, user_id, amount):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("UPDATE users SET credits = credits - ? WHERE user_id = ?", (amount, user_id))
        conn.commit(); conn.close()
    def use_credits(self, user_id, amount):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("UPDATE users SET credits = credits - ?, total_used_credits = total_used_credits + ? WHERE user_id = ?", (amount, amount, user_id))
        conn.commit(); conn.close()
    def add_zip_history(self, user_id, url, zip_file_name, total_files):
        conn = self.get_conn(); c = conn.cursor()
        ct = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO zip_history (user_id, url, zip_file_name, total_files, created_time) VALUES (?, ?, ?, ?, ?)",
                  (user_id, url, zip_file_name, total_files, ct))
        c.execute("UPDATE users SET total_generated_zips = total_generated_zips + 1 WHERE user_id = ?", (user_id,))
        conn.commit(); conn.close()
    def get_zip_history(self, user_id):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM zip_history WHERE user_id = ? ORDER BY id DESC", (user_id,))
        r = c.fetchall(); conn.close(); return r
    def get_channels(self):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM channels"); r = c.fetchall(); conn.close(); return r
    def add_channel(self, name, link):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("INSERT INTO channels (channel_name, channel_link) VALUES (?, ?)", (name, link))
        conn.commit(); conn.close()
    def delete_channel(self, channel_id):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
        conn.commit(); conn.close()
    def edit_channel(self, channel_id, name, link):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("UPDATE channels SET channel_name = ?, channel_link = ? WHERE id = ?", (name, link, channel_id))
        conn.commit(); conn.close()
    def get_plans(self):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM plans"); r = c.fetchall(); conn.close(); return r
    def add_plan(self, title, price):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("INSERT INTO plans (title, price) VALUES (?, ?)", (title, price))
        conn.commit(); conn.close()
    def delete_plan(self, plan_id):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
        conn.commit(); conn.close()
    def edit_plan(self, plan_id, title, price):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("UPDATE plans SET title = ?, price = ? WHERE id = ?", (title, price, plan_id))
        conn.commit(); conn.close()
    def get_bots(self):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM bots_marketplace"); r = c.fetchall(); conn.close(); return r
    def add_bot(self, username, link, description):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("INSERT INTO bots_marketplace (bot_username, bot_link, description) VALUES (?, ?, ?)", (username, link, description))
        conn.commit(); conn.close()
    def delete_bot(self, bot_id):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("DELETE FROM bots_marketplace WHERE id = ?", (bot_id,))
        conn.commit(); conn.close()
    def edit_bot(self, bot_id, username, link, description):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("UPDATE bots_marketplace SET bot_username = ?, bot_link = ?, description = ? WHERE id = ?", (username, link, description, bot_id))
        conn.commit(); conn.close()
    def get_apis(self):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM api_marketplace"); r = c.fetchall(); conn.close(); return r
    def add_api(self, title, description):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("INSERT INTO api_marketplace (api_title, api_description) VALUES (?, ?)", (title, description))
        conn.commit(); conn.close()
    def delete_api(self, api_id):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("DELETE FROM api_marketplace WHERE id = ?", (api_id,))
        conn.commit(); conn.close()
    def edit_api(self, api_id, title, description):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("UPDATE api_marketplace SET api_title = ?, api_description = ? WHERE id = ?", (title, description, api_id))
        conn.commit(); conn.close()
    def add_request(self, user_id, group_link, reason):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("INSERT INTO requests (user_id, group_link, reason) VALUES (?, ?, ?)", (user_id, group_link, reason))
        conn.commit(); conn.close()
    def get_requests(self):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM requests WHERE status = 'pending'"); r = c.fetchall(); conn.close(); return r
    def update_request(self, req_id, status):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("UPDATE requests SET status = ? WHERE id = ?", (status, req_id))
        conn.commit(); conn.close()
    def ban_user(self, user_id):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("UPDATE users SET banned_status = 1 WHERE user_id = ?", (user_id,))
        conn.commit(); conn.close()
    def unban_user(self, user_id):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("UPDATE users SET banned_status = 0 WHERE user_id = ?", (user_id,))
        conn.commit(); conn.close()
    def get_all_users(self):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("SELECT user_id FROM users"); r = c.fetchall(); conn.close(); return [x[0] for x in r]
    def get_stats(self):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users"); tu = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users WHERE premium_status = 1"); pu = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users WHERE premium_status = 0"); fu = c.fetchone()[0]
        c.execute("SELECT SUM(total_generated_zips) FROM users"); gz = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM users WHERE banned_status = 0"); au = c.fetchone()[0]
        c.execute("SELECT SUM(total_used_credits) FROM users"); tc = c.fetchone()[0] or 0
        c.execute("SELECT SUM(referral_count) FROM users"); tr = c.fetchone()[0] or 0
        conn.close()
        return {'total_users': tu, 'premium_users': pu, 'free_users': fu, 'generated_zips': gz, 'active_users': au, 'total_credits_used': tc, 'total_referrals': tr}
    def search_user(self, username):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username LIKE ?", (f"%{username}%",))
        r = c.fetchall(); conn.close(); return r
    def get_premium_users(self):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM users WHERE premium_status = 1"); r = c.fetchall(); conn.close(); return r
    def process_referral(self, new_user_id, referral_code):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE referral_code = ?", (referral_code,))
        owner = c.fetchone()
        if owner and owner[0] != new_user_id:
            oid = owner[0]; s = self.get_settings()
            c.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (s['referral_user_credit'], new_user_id))
            c.execute("UPDATE users SET credits = credits + ?, referral_count = referral_count + 1 WHERE user_id = ?", (s['referral_owner_credit'], oid))
            c.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (oid, new_user_id))
            conn.commit()
        conn.close()
    def add_premium(self, user_id, plan, days):
        conn = self.get_conn(); c = conn.cursor()
        ed = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("UPDATE users SET premium_status = 1, premium_plan = ?, premium_expire_date = ? WHERE user_id = ?", (plan, ed, user_id))
        conn.commit(); conn.close()
    def get_zip_logs(self):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM zip_history ORDER BY id DESC LIMIT 50"); r = c.fetchall(); conn.close(); return r
    def get_referral_logs(self):
        conn = self.get_conn(); c = conn.cursor()
        c.execute("SELECT user_id, referral_code, referral_count, referred_by FROM users WHERE referral_count > 0 OR referred_by > 0")
        r = c.fetchall(); conn.close(); return r

class Form(StatesGroup):
    url_input = State(); channel_name = State(); channel_link = State()
    plan_title = State(); plan_price = State()
    bot_username = State(); bot_link = State(); bot_desc = State()
    api_title = State(); api_desc = State()
    group_link = State(); group_reason = State()
    broadcast_msg = State(); search_username = State()
    add_credits_user = State(); add_credits_amount = State()
    remove_credits_user = State(); remove_credits_amount = State()
    settings_new_user = State(); settings_ref_user = State()
    settings_ref_owner = State(); settings_zip_cost = State()
    settings_maintenance_msg = State()
    edit_channel_name = State(); edit_channel_link = State()
    edit_plan_title = State(); edit_plan_price = State()
    edit_bot_username = State(); edit_bot_link = State(); edit_bot_desc = State()
    edit_api_title = State(); edit_api_desc = State()
    referral_code_input = State(); ban_user_id = State(); unban_user_id = State()

db = Database(DB_FILE)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🌐 Enter URL"), KeyboardButton(text="📦 My Source Code")],
            [KeyboardButton(text="👤 User Profile"), KeyboardButton(text="💎 Premium Plans")],
            [KeyboardButton(text="🔗 Referral"), KeyboardButton(text="💰 Buy Credits")],
            [KeyboardButton(text="🤖 Buy This Bot Source Code"), KeyboardButton(text="🛒 Buy All Bot Source Code")],
            [KeyboardButton(text="🔑 Buy API Key"), KeyboardButton(text="📋 All Bots")],
            [KeyboardButton(text="❓ Help"), KeyboardButton(text="📊 Status")],
            [KeyboardButton(text="➕ Add Bot In Your Group")],
        ], resize_keyboard=True)

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Ban User", callback_data="admin_ban"), InlineKeyboardButton(text="✅ Unban User", callback_data="admin_unban")],
        [InlineKeyboardButton(text="🔧 Maintenance ON", callback_data="admin_maint_on"), InlineKeyboardButton(text="🔧 Maintenance OFF", callback_data="admin_maint_off")],
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📢 Force Join Manager", callback_data="admin_force_join")],
        [InlineKeyboardButton(text="📊 Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🔍 Search User", callback_data="admin_search")],
        [InlineKeyboardButton(text="💎 Add Premium Plan", callback_data="admin_add_plan"), InlineKeyboardButton(text="🗑 Delete Premium Plan", callback_data="admin_del_plan")],
        [InlineKeyboardButton(text="✏️ Edit Premium Plan", callback_data="admin_edit_plan")],
        [InlineKeyboardButton(text="🤖 Add Bot", callback_data="admin_add_bot"), InlineKeyboardButton(text="🗑 Delete Bot", callback_data="admin_del_bot")],
        [InlineKeyboardButton(text="✏️ Edit Bot", callback_data="admin_edit_bot")],
        [InlineKeyboardButton(text="🔑 Add API", callback_data="admin_add_api"), InlineKeyboardButton(text="🗑 Delete API", callback_data="admin_del_api")],
        [InlineKeyboardButton(text="✏️ Edit API", callback_data="admin_edit_api")],
        [InlineKeyboardButton(text="📋 Check User Requests", callback_data="admin_requests")],
        [InlineKeyboardButton(text="⚙️ Settings", callback_data="admin_settings")],
        [InlineKeyboardButton(text="➕ Add Credits", callback_data="admin_add_credits"), InlineKeyboardButton(text="➖ Remove Credits", callback_data="admin_remove_credits")],
        [InlineKeyboardButton(text="📦 View ZIP Logs", callback_data="admin_zip_logs")],
        [InlineKeyboardButton(text="🔗 View Referral Logs", callback_data="admin_ref_logs")],
        [InlineKeyboardButton(text="💎 View Premium Users", callback_data="admin_premium_users")],
        [InlineKeyboardButton(text="📤 Export Database", callback_data="admin_export_db")],
        [InlineKeyboardButton(text="💾 Backup Database", callback_data="admin_backup_db")],
    ])

def is_admin(user_id): return user_id == ADMIN_ID

async def check_maintenance(message: Message):
    s = db.get_settings()
    if s['maintenance_mode'] and not is_admin(message.from_user.id):
        await message.answer(s['maintenance_message']); return True
    return False

async def check_banned(user_id):
    u = db.get_user(user_id)
    return u and u[13] == 1

async def check_force_join(user_id, bot_instance):
    chs = db.get_channels()
    if not chs: return True
    nj = []
    for ch in chs:
        try:
            m = await bot_instance.get_chat_member(ch[2], user_id)
            if m.status in ["left", "kicked"]: nj.append(ch)
        except: nj.append(ch)
    return nj

async def send_force_join(message, channels):
    t = "⚠️ <b>Please join the following channels to use this bot:</b>\n\n"
    kb = []
    for ch in channels:
        t += f"• {ch[1]}\n"
        kb.append([InlineKeyboardButton(text=f"Join {ch[1]}", url=ch[2])])
    kb.append([InlineKeyboardButton(text="✅ Check Membership", callback_data="check_membership")])
    await message.answer(t, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    if await check_maintenance(message): return
    uid = message.from_user.id; u = db.get_user(uid)
    args = message.text.split()
    if len(args) > 1 and not u: db.process_referral(uid, args[1])
    if not u: db.add_user(uid, message.from_user.username, message.from_user.first_name)
    if await check_banned(uid):
        await message.answer("🚫 You are banned from using this bot."); return
    nj = await check_force_join(uid, bot)
    if nj != True: await send_force_join(message, nj); return
    w = f"""👋 <b>Welcome to Ultimate Website Source Extractor!</b>

🌐 Submit any website URL and I'll download all publicly accessible files, preserve the folder structure, and send you a ZIP archive.

💳 You have <b>{db.get_user(uid)[4]}</b> credits.

👨‍💻 <b>Developer:</b> RAI DEVELOPER"""
    await message.answer(w, reply_markup=main_menu(), parse_mode="HTML")

@router.callback_query(F.data == "check_membership")
async def check_membership(callback: CallbackQuery):
    nj = await check_force_join(callback.from_user.id, bot)
    if nj != True:
        await callback.answer("❌ You haven't joined all channels yet!")
        await send_force_join(callback.message, nj)
    else:
        await callback.answer("✅ Membership verified!")
        await callback.message.delete()
        await cmd_start(callback.message, None)

@router.message(F.text == "🌐 Enter URL")
async def enter_url(message: Message, state: FSMContext):
    if await check_maintenance(message): return
    if await check_banned(message.from_user.id): await message.answer("🚫 You are banned."); return
    nj = await check_force_join(message.from_user.id, bot)
    if nj != True: await send_force_join(message, nj); return
    await state.set_state(Form.url_input)
    await message.answer("🌐 <b>Enter Website URL</b>\n\nExample:\n<code>https://google.com</code>", parse_mode="HTML")

@router.message(Form.url_input)
async def process_url(message: Message, state: FSMContext):
    await state.clear(); url = message.text.strip(); uid = message.from_user.id
    u = db.get_user(uid); s = db.get_settings()
    if not url.startswith(("http://", "https://")):
        await message.answer("❌ Invalid URL. Please provide a valid URL starting with http:// or https://"); return
    if u[4] < s['zip_cost']:
        await message.answer("❌ <b>Insufficient Credits!</b>\n\nPlease buy more credits or use a referral code.", parse_mode="HTML"); return
    pm = await message.answer("⏳ <b>Processing...</b>\n\n🔍 Analyzing website structure...", parse_mode="HTML")
    try:
        zp, tf = await extract_website(url, uid, pm)
        if zp and os.path.exists(zp):
            db.use_credits(uid, s['zip_cost']); zn = os.path.basename(zp)
            db.add_zip_history(uid, url, zn, tf)
            zs = os.path.getsize(zp)
            ss = f"{zs / 1024 / 1024:.2f} MB" if zs > 1024*1024 else f"{zs / 1024:.2f} KB"
            cap = f"""📦 <b>Website Source Extracted!</b>

🌐 <b>URL:</b> {url}
💳 <b>Credits Used:</b> {s['zip_cost']}
📁 <b>Files Found:</b> {tf}
📊 <b>ZIP Size:</b> {ss}
⏰ <b>Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

👨‍💻 <b>Developer:</b> RAI DEVELOPER"""
            await pm.delete()
            await message.answer_document(FSInputFile(zp), caption=cap, parse_mode="HTML")
            try:
                os.remove(zp)
                sd = os.path.join(DOWNLOAD_DIR, str(uid), urlparse(url).netloc)
                if os.path.exists(sd): shutil.rmtree(sd)
            except: pass
        else: await pm.edit_text("❌ Failed to extract website. Please try again.")
    except Exception as e: await pm.edit_text(f"❌ Error: {str(e)[:200]}")

async def extract_website(url, user_id, status_msg):
    p = urlparse(url); bu = f"{p.scheme}://{p.netloc}"; dm = p.netloc.replace(":", "_")
    ud = os.path.join(DOWNLOAD_DIR, str(user_id)); sd = os.path.join(ud, dm)
    os.makedirs(sd, exist_ok=True)
    dl = set(); tf = [0]
    async def df(session, fu, rp):
        if fu in dl: return
        dl.add(fu)
        try:
            async with session.get(fu, timeout=aiohttp.ClientTimeout(total=30), ssl=False) as r:
                if r.status == 200:
                    ct = await r.read(); fp = os.path.join(sd, rp)
                    os.makedirs(os.path.dirname(fp), exist_ok=True)
                    async with aiofiles.open(fp, 'wb') as f: await f.write(ct)
                    tf[0] += 1
        except: pass
    async def pp(session, pu, d=0):
        if d > 2: return
        try:
            h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            async with session.get(pu, timeout=aiohttp.ClientTimeout(total=30), headers=h, ssl=False) as r:
                if r.status != 200: return
                ct = r.headers.get('content-type', '')
                if 'text/html' not in ct: return
                html = await r.text(); sp = BeautifulSoup(html, 'html.parser')
                ts = []
                for l in sp.find_all('link', rel='stylesheet'):
                    hr = l.get('href')
                    if hr:
                        fu = urljoin(bu, hr); ph = urlparse(fu)
                        if ph.netloc == p.netloc:
                            rl = ph.path.lstrip('/')
                            if rl: ts.append(df(session, fu, rl))
                for sc in sp.find_all('script', src=True):
                    sr = sc.get('src')
                    if sr:
                        fu = urljoin(bu, sr); ps = urlparse(fu)
                        if ps.netloc == p.netloc:
                            rl = ps.path.lstrip('/')
                            if rl: ts.append(df(session, fu, rl))
                for im in sp.find_all('img', src=True):
                    sr = im.get('src')
                    if sr:
                        fu = urljoin(bu, sr); pi = urlparse(fu)
                        if pi.netloc == p.netloc:
                            rl = pi.path.lstrip('/')
                            if rl: ts.append(df(session, fu, rl))
                for l in sp.find_all('link'):
                    if l.get('rel') == ['preload'] and l.get('as') == 'font':
                        hr = l.get('href')
                        if hr:
                            fu = urljoin(bu, hr); pf = urlparse(fu)
                            if pf.netloc == p.netloc:
                                rl = pf.path.lstrip('/')
                                if rl: ts.append(df(session, fu, rl))
                if ts: await asyncio.gather(*ts)
                pp_ = urlparse(pu).path.lstrip('/')
                if not pp_ or pp_.endswith('/'): pp_ = os.path.join(pp_, 'index.html')
                if not pp_.endswith('.html'): pp_ += '.html'
                hp = os.path.join(sd, pp_); os.makedirs(os.path.dirname(hp), exist_ok=True)
                async with aiofiles.open(hp, 'w', encoding='utf-8') as f: await f.write(html)
                if hp not in dl: tf[0] += 1; dl.add(hp)
                if d < 1:
                    lt = []
                    for a in sp.find_all('a', href=True):
                        hr = a.get('href')
                        if hr:
                            fu = urljoin(bu, hr); pl = urlparse(fu)
                            if pl.netloc == p.netloc and fu not in dl: lt.append(pp(session, fu, d + 1))
                    if lt: await asyncio.gather(*lt[:10])
        except: pass
    cn = aiohttp.TCPConnector(limit=50, limit_per_host=20)
    async with aiohttp.ClientSession(connector=cn) as session: await pp(session, url)
    zn = f"{dm}.zip"; zp = os.path.join(ud, zn)
    with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as zf:
        for rt, ds, fs in os.walk(sd):
            for f in fs:
                fp = os.path.join(rt, f); an = os.path.relpath(fp, sd); zf.write(fp, an)
    return zp, tf[0]

@router.message(F.text == "📦 My Source Code")
async def my_source_code(message: Message):
    if await check_maintenance(message): return
    if await check_banned(message.from_user.id): await message.answer("🚫 You are banned."); return
    nj = await check_force_join(message.from_user.id, bot)
    if nj != True: await send_force_join(message, nj); return
    h = db.get_zip_history(message.from_user.id)
    if not h:
        await message.answer("📭 <b>No source codes found.</b>\n\nUse 🌐 Enter URL to extract a website.", parse_mode="HTML"); return
    t = "📦 <b>Your Source Code History</b>\n\n"
    for i in h[:10]: t += f"🌐 <b>URL:</b> {i[2]}\n📁 <b>Files:</b> {i[4]}\n📅 <b>Date:</b> {i[5]}\n\n"
    await message.answer(t, parse_mode="HTML")

@router.message(F.text == "👤 User Profile")
async def user_profile(message: Message):
    if await check_maintenance(message): return
    if await check_banned(message.from_user.id): await message.answer("🚫 You are banned."); return
    nj = await check_force_join(message.from_user.id, bot)
    if nj != True: await send_force_join(message, nj); return
    u = db.get_user(message.from_user.id)
    if not u: await message.answer("❌ User not found."); return
    pt = u[11] if u[11] else "Free"; ps = "💎 Premium" if u[10] else "🆓 Free"
    t = f"""👤 <b>User Profile</b>

📝 <b>Name:</b> {u[2]}
🔗 <b>Username:</b> @{u[1] if u[1] else 'N/A'}
🆔 <b>User ID:</b> <code>{u[0]}</code>
💳 <b>Credits:</b> {u[4]}
💰 <b>Used Credits:</b> {u[5]}
📦 <b>Generated ZIPs:</b> {u[6]}
🔗 <b>Referral Count:</b> {u[9]}
💎 <b>Plan Type:</b> {ps} ({pt})
📅 <b>Join Date:</b> {u[3]}

🔗 <b>Referral Code:</b> <code>{u[7]}</code>"""
    await message.answer(t, parse_mode="HTML")

@router.message(F.text == "💎 Premium Plans")
async def premium_plans(message: Message):
    if await check_maintenance(message): return
    if await check_banned(message.from_user.id): await message.answer("🚫 You are banned."); return
    nj = await check_force_join(message.from_user.id, bot)
    if nj != True: await send_force_join(message, nj); return
    pl = db.get_plans()
    if not pl:
        await message.answer("💎 <b>Premium Plans</b>\n\nNo plans available at the moment. Contact admin for details.", parse_mode="HTML"); return
    t = "💎 <b>Premium Plans</b>\n\n"; kb = []
    for p in pl: t += f"📌 <b>{p[1]}</b> - {p[2]}\n\n"; kb.append([InlineKeyboardButton(text=f"Buy {p[1]} - {p[2]}", url="https://t.me/Subhash_Anuragi_RAI")])
    await message.answer(t, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@router.message(F.text == "🔗 Referral")
async def referral(message: Message):
    if await check_maintenance(message): return
    if await check_banned(message.from_user.id): await message.answer("🚫 You are banned."); return
    nj = await check_force_join(message.from_user.id, bot)
    if nj != True: await send_force_join(message, nj); return
    u = db.get_user(message.from_user.id)
    if not u: await message.answer("❌ User not found."); return
    bi = await bot.get_me(); rl = f"https://t.me/{bi.username}?start={u[7]}"
    t = f"""🔗 <b>Referral Program</b>

🎁 <b>Your Referral Code:</b> <code>{u[7]}</code>
🔗 <b>Your Referral Link:</b>
<code>{rl}</code>

🎉 <b>Rewards:</b>
• New User: +2 Credits
• You: +1 Credit per referral

📊 <b>Total Referrals:</b> {u[9]}

Share your link with friends and earn credits!"""
    await message.answer(t, parse_mode="HTML")

@router.message(F.text == "💰 Buy Credits")
async def buy_credits(message: Message):
    if await check_maintenance(message): return
    if await check_banned(message.from_user.id): await message.answer("🚫 You are banned."); return
    nj = await check_force_join(message.from_user.id, bot)
    if nj != True: await send_force_join(message, nj); return
    t = """💰 <b>Buy Credits</b>

Contact the admin to purchase credits.

👨‍💻 <b>Developer:</b> @Subhash_Anuragi_RAI"""
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📩 Contact Admin", url="https://t.me/Subhash_Anuragi_RAI")]])
    await message.answer(t, reply_markup=kb, parse_mode="HTML")

@router.message(F.text == "🤖 Buy This Bot Source Code")
async def buy_this_bot(message: Message):
    if await check_maintenance(message): return
    if await check_banned(message.from_user.id): await message.answer("🚫 You are banned."); return
    nj = await check_force_join(message.from_user.id, bot)
    if nj != True: await send_force_join(message, nj); return
    t = """🤖 <b>Buy This Bot Source Code</b>

Get the complete source code of this bot.

👨‍💻 <b>Developer:</b> @Subhash_Anuragi_RAI"""
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📩 Contact Admin", url="https://t.me/Subhash_Anuragi_RAI")]])
    await message.answer(t, reply_markup=kb, parse_mode="HTML")

@router.message(F.text == "🛒 Buy All Bot Source Code")
async def buy_all_bots(message: Message):
    if await check_maintenance(message): return
    if await check_banned(message.from_user.id): await message.answer("🚫 You are banned."); return
    nj = await check_force_join(message.from_user.id, bot)
    if nj != True: await send_force_join(message, nj); return
    t = """🛒 <b>Buy All Bot Source Code</b>

Get access to all bot source codes from our collection.

👨‍💻 <b>Developer:</b> @Subhash_Anuragi_RAI"""
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📩 Contact Admin", url="https://t.me/Subhash_Anuragi_RAI")]])
    await message.answer(t, reply_markup=kb, parse_mode="HTML")

@router.message(F.text == "🔑 Buy API Key")
async def buy_api_key(message: Message):
    if await check_maintenance(message): return
    if await check_banned(message.from_user.id): await message.answer("🚫 You are banned."); return
    nj = await check_force_join(message.from_user.id, bot)
    if nj != True: await send_force_join(message, nj); return
    ap = db.get_apis()
    if not ap:
        await message.answer("🔑 <b>API Marketplace</b>\n\nNo APIs available at the moment.", parse_mode="HTML"); return
    t = "🔑 <b>API Marketplace</b>\n\n"; kb = []
    for a in ap: t += f"📌 <b>{a[1]}</b>\n{a[2]}\n\n"; kb.append([InlineKeyboardButton(text=f"Buy {a[1]}", url="https://t.me/Subhash_Anuragi_RAI")])
    await message.answer(t, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@router.message(F.text == "📋 All Bots")
async def all_bots(message: Message):
    if await check_maintenance(message): return
    if await check_banned(message.from_user.id): await message.answer("🚫 You are banned."); return
    nj = await check_force_join(message.from_user.id, bot)
    if nj != True: await send_force_join(message, nj); return
    bs = db.get_bots()
    if not bs:
        await message.answer("📋 <b>Bot Marketplace</b>\n\nNo bots available at the moment.", parse_mode="HTML"); return
    for b in bs:
        t = f"""🤖 <b>{b[1]}</b>

📝 <b>Description:</b> {b[3]}"""
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔗 Open Bot", url=b[2])]])
        await message.answer(t, reply_markup=kb, parse_mode="HTML")

@router.message(F.text == "❓ Help")
async def help_section(message: Message):
    if await check_maintenance(message): return
    if await check_banned(message.from_user.id): await message.answer("🚫 You are banned."); return
    nj = await check_force_join(message.from_user.id, bot)
    if nj != True: await send_force_join(message, nj); return
    t = """❓ <b>Help Section</b>

🌐 <b>/start</b> - Start the bot
🌐 <b>Enter URL</b> - Extract website source code
📦 <b>My Source Code</b> - View your extraction history
👤 <b>User Profile</b> - View your profile
💎 <b>Premium Plans</b> - View premium plans
🔗 <b>Referral</b> - Get your referral link
💰 <b>Buy Credits</b> - Purchase credits
🤖 <b>Buy This Bot Source Code</b> - Purchase this bot
🛒 <b>Buy All Bot Source Code</b> - Purchase all bots
🔑 <b>Buy API Key</b> - Purchase API keys
📋 <b>All Bots</b> - Browse bot marketplace
📊 <b>Status</b> - Bot statistics
➕ <b>Add Bot In Your Group</b> - Request bot addition

👨‍💻 <b>Developer:</b> @Subhash_Anuragi_RAI"""
    await message.answer(t, parse_mode="HTML")

@router.message(F.text == "📊 Status")
async def status_section(message: Message):
    if await check_maintenance(message): return
    if await check_banned(message.from_user.id): await message.answer("🚫 You are banned."); return
    nj = await check_force_join(message.from_user.id, bot)
    if nj != True: await send_force_join(message, nj); return
    st = db.get_stats()
    t = f"""📊 <b>Bot Status</b>

👥 <b>Total Users:</b> {st['total_users']}
💎 <b>Premium Users:</b> {st['premium_users']}
🆓 <b>Free Users:</b> {st['free_users']}
📦 <b>Generated ZIPs:</b> {st['generated_zips']}
✅ <b>Active Users:</b> {st['active_users']}
💰 <b>Total Credits Used:</b> {st['total_credits_used']}
🔗 <b>Total Referrals:</b> {st['total_referrals']}

👨‍💻 <b>Developer:</b> RAI DEVELOPER"""
    await message.answer(t, parse_mode="HTML")

@router.message(F.text == "➕ Add Bot In Your Group")
async def add_bot_group(message: Message, state: FSMContext):
    if await check_maintenance(message): return
    if await check_banned(message.from_user.id): await message.answer("🚫 You are banned."); return
    nj = await check_force_join(message.from_user.id, bot)
    if nj != True: await send_force_join(message, nj); return
    await state.set_state(Form.group_link)
    await message.answer("🔗 <b>Enter Your Group Link:</b>\n\nExample: https://t.me/yourgroup", parse_mode="HTML")

@router.message(Form.group_link)
async def process_group_link(message: Message, state: FSMContext):
    await state.update_data(group_link=message.text)
    await state.set_state(Form.group_reason)
    await message.answer("📝 <b>Enter Reason for Adding Bot:</b>", parse_mode="HTML")

@router.message(Form.group_reason)
async def process_group_reason(message: Message, state: FSMContext):
    d = await state.get_data(); gl = d['group_link']; rs = message.text; uid = message.from_user.id
    db.add_request(uid, gl, rs); await state.clear()
    await message.answer("✅ <b>Request Submitted!</b>\n\nAdmin will review your request soon.", parse_mode="HTML")
    try:
        at = f"""📋 <b>New Group Request</b>

👤 <b>User:</b> {message.from_user.first_name}
🆔 <b>User ID:</b> <code>{uid}</code>
🔗 <b>Group Link:</b> {gl}
📝 <b>Reason:</b> {rs}"""
        await bot.send_message(ADMIN_ID, at, parse_mode="HTML")
    except: pass

@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("🚫 You are not authorized to use this command."); return
    await message.answer("🔧 <b>Admin Panel</b>\n\nSelect an option:", reply_markup=admin_menu(), parse_mode="HTML")

@router.callback_query(F.data == "admin_ban")
async def admin_ban(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.ban_user_id)
    await callback.message.answer("🚫 <b>Enter User ID to Ban:</b>", parse_mode="HTML")

@router.callback_query(F.data == "admin_unban")
async def admin_unban(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.unban_user_id)
    await callback.message.answer("✅ <b>Enter User ID to Unban:</b>", parse_mode="HTML")

@router.message(Form.ban_user_id)
async def process_ban_user(message: Message, state: FSMContext):
    try:
        uid = int(message.text); db.ban_user(uid)
        await message.answer(f"🚫 <b>User {uid} has been banned.</b>", parse_mode="HTML")
    except: await message.answer("❌ Invalid User ID.")
    await state.clear()

@router.message(Form.unban_user_id)
async def process_unban_user(message: Message, state: FSMContext):
    try:
        uid = int(message.text); db.unban_user(uid)
        await message.answer(f"✅ <b>User {uid} has been unbanned.</b>", parse_mode="HTML")
    except: await message.answer("❌ Invalid User ID.")
    await state.clear()

@router.callback_query(F.data == "admin_maint_on")
async def admin_maint_on(callback: CallbackQuery):
    db.update_settings(maintenance_mode=1)
    await callback.message.answer("🔧 <b>Maintenance Mode ON</b>", parse_mode="HTML")

@router.callback_query(F.data == "admin_maint_off")
async def admin_maint_off(callback: CallbackQuery):
    db.update_settings(maintenance_mode=0)
    await callback.message.answer("🔧 <b>Maintenance Mode OFF</b>", parse_mode="HTML")

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.broadcast_msg)
    await callback.message.answer("📢 <b>Enter message to broadcast:</b>", parse_mode="HTML")

@router.message(Form.broadcast_msg)
async def process_broadcast(message: Message, state: FSMContext):
    await state.clear(); us = db.get_all_users(); sc = 0; fc = 0
    for uid in us:
        try: await bot.copy_message(uid, message.chat.id, message.message_id); sc += 1; await asyncio.sleep(0.05)
        except: fc += 1
    await message.answer(f"📢 <b>Broadcast Complete!</b>\n\n✅ Success: {sc}\n❌ Failed: {fc}", parse_mode="HTML")

@router.callback_query(F.data == "admin_force_join")
async def admin_force_join(callback: CallbackQuery):
    chs = db.get_channels(); t = "📢 <b>Force Join Channels</b>\n\n"; kb = []
    for ch in chs:
        t += f"{ch[0]}. {ch[1]} - {ch[2]}\n"
        kb.append([InlineKeyboardButton(text=f"🗑 Delete {ch[1]}", callback_data=f"del_channel_{ch[0]}")])
        kb.append([InlineKeyboardButton(text=f"✏️ Edit {ch[1]}", callback_data=f"edit_channel_{ch[0]}")])
    kb.append([InlineKeyboardButton(text="➕ Add Channel", callback_data="add_channel")])
    await callback.message.answer(t, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@router.callback_query(F.data == "add_channel")
async def add_channel(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.channel_name)
    await callback.message.answer("📢 <b>Enter Channel Name:</b>", parse_mode="HTML")

@router.message(Form.channel_name)
async def process_channel_name(message: Message, state: FSMContext):
    await state.update_data(channel_name=message.text)
    await state.set_state(Form.channel_link)
    await message.answer("🔗 <b>Enter Channel Link:</b>\n\nExample: @channelname or https://t.me/channelname", parse_mode="HTML")

@router.message(Form.channel_link)
async def process_channel_link(message: Message, state: FSMContext):
    d = await state.get_data(); db.add_channel(d['channel_name'], message.text); await state.clear()
    await message.answer("✅ <b>Channel Added!</b>", parse_mode="HTML")

@router.callback_query(F.data.startswith("del_channel_"))
async def del_channel(callback: CallbackQuery):
    cid = int(callback.data.split("_")[2]); db.delete_channel(cid)
    await callback.message.answer("🗑 <b>Channel Deleted!</b>", parse_mode="HTML")

@router.callback_query(F.data.startswith("edit_channel_"))
async def edit_channel_start(callback: CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2]); await state.update_data(edit_channel_id=cid)
    await state.set_state(Form.edit_channel_name)
    await callback.message.answer("✏️ <b>Enter New Channel Name:</b>", parse_mode="HTML")

@router.message(Form.edit_channel_name)
async def process_edit_channel_name(message: Message, state: FSMContext):
    await state.update_data(edit_channel_name=message.text)
    await state.set_state(Form.edit_channel_link)
    await message.answer("🔗 <b>Enter New Channel Link:</b>", parse_mode="HTML")

@router.message(Form.edit_channel_link)
async def process_edit_channel_link(message: Message, state: FSMContext):
    d = await state.get_data(); db.edit_channel(d['edit_channel_id'], d['edit_channel_name'], message.text); await state.clear()
    await message.answer("✅ <b>Channel Updated!</b>", parse_mode="HTML")

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    st = db.get_stats()
    t = f"""📊 <b>Bot Statistics</b>

👥 <b>Total Users:</b> {st['total_users']}
💎 <b>Premium Users:</b> {st['premium_users']}
🆓 <b>Free Users:</b> {st['free_users']}
📦 <b>Generated ZIPs:</b> {st['generated_zips']}
✅ <b>Active Users:</b> {st['active_users']}
💰 <b>Total Credits Used:</b> {st['total_credits_used']}
🔗 <b>Total Referrals:</b> {st['total_referrals']}"""
    await callback.message.answer(t, parse_mode="HTML")

@router.callback_query(F.data == "admin_search")
async def admin_search(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.search_username)
    await callback.message.answer("🔍 <b>Enter Username to Search:</b>", parse_mode="HTML")

@router.message(Form.search_username)
async def process_search(message: Message, state: FSMContext):
    await state.clear(); us = db.search_user(message.text)
    if not us: await message.answer("❌ No users found."); return
    for u in us:
        pr = "💎 Premium" if u[10] else "🆓 Free"; h = db.get_zip_history(u[0])
        t = f"""👤 <b>User Found</b>

🆔 <b>User ID:</b> <code>{u[0]}</code>
📝 <b>Name:</b> {u[2]}
🔗 <b>Username:</b> @{u[1] if u[1] else 'N/A'}
💳 <b>Credits:</b> {u[4]}
📦 <b>ZIP Count:</b> {u[6]}
🔗 <b>Referral Count:</b> {u[9]}
💎 <b>Premium:</b> {pr}
📅 <b>Join Date:</b> {u[3]}

📦 <b>History:</b> {len(h)} extractions"""
        await message.answer(t, parse_mode="HTML")

@router.callback_query(F.data == "admin_add_plan")
async def admin_add_plan(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.plan_title)
    await callback.message.answer("💎 <b>Enter Plan Title:</b>\n\nExample: 1 Month", parse_mode="HTML")

@router.message(Form.plan_title)
async def process_plan_title(message: Message, state: FSMContext):
    await state.update_data(plan_title=message.text)
    await state.set_state(Form.plan_price)
    await message.answer("💰 <b>Enter Plan Price:</b>\n\nExample: ₹99", parse_mode="HTML")

@router.message(Form.plan_price)
async def process_plan_price(message: Message, state: FSMContext):
    d = await state.get_data(); db.add_plan(d['plan_title'], message.text); await state.clear()
    await message.answer("✅ <b>Plan Added!</b>", parse_mode="HTML")

@router.callback_query(F.data == "admin_del_plan")
async def admin_del_plan(callback: CallbackQuery):
    pl = db.get_plans(); kb = []
    for p in pl: kb.append([InlineKeyboardButton(text=f"🗑 {p[1]} - {p[2]}", callback_data=f"del_plan_{p[0]}")])
    await callback.message.answer("🗑 <b>Select Plan to Delete:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@router.callback_query(F.data.startswith("del_plan_"))
async def process_del_plan(callback: CallbackQuery):
    pid = int(callback.data.split("_")[2]); db.delete_plan(pid)
    await callback.message.answer("🗑 <b>Plan Deleted!</b>", parse_mode="HTML")

@router.callback_query(F.data == "admin_edit_plan")
async def admin_edit_plan(callback: CallbackQuery):
    pl = db.get_plans(); kb = []
    for p in pl: kb.append([InlineKeyboardButton(text=f"✏️ {p[1]} - {p[2]}", callback_data=f"edit_plan_{p[0]}")])
    await callback.message.answer("✏️ <b>Select Plan to Edit:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@router.callback_query(F.data.startswith("edit_plan_"))
async def process_edit_plan_start(callback: CallbackQuery, state: FSMContext):
    pid = int(callback.data.split("_")[2]); await state.update_data(edit_plan_id=pid)
    await state.set_state(Form.edit_plan_title)
    await callback.message.answer("✏️ <b>Enter New Plan Title:</b>", parse_mode="HTML")

@router.message(Form.edit_plan_title)
async def process_edit_plan_title(message: Message, state: FSMContext):
    await state.update_data(edit_plan_title=message.text)
    await state.set_state(Form.edit_plan_price)
    await message.answer("💰 <b>Enter New Plan Price:</b>", parse_mode="HTML")

@router.message(Form.edit_plan_price)
async def process_edit_plan_price(message: Message, state: FSMContext):
    d = await state.get_data(); db.edit_plan(d['edit_plan_id'], d['edit_plan_title'], message.text); await state.clear()
    await message.answer("✅ <b>Plan Updated!</b>", parse_mode="HTML")

@router.callback_query(F.data == "admin_add_bot")
async def admin_add_bot(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.bot_username)
    await callback.message.answer("🤖 <b>Enter Bot Username:</b>\n\nExample: @mybot", parse_mode="HTML")

@router.message(Form.bot_username)
async def process_bot_username(message: Message, state: FSMContext):
    await state.update_data(bot_username=message.text)
    await state.set_state(Form.bot_link)
    await message.answer("🔗 <b>Enter Bot Link:</b>\n\nExample: https://t.me/mybot", parse_mode="HTML")

@router.message(Form.bot_link)
async def process_bot_link(message: Message, state: FSMContext):
    await state.update_data(bot_link=message.text)
    await state.set_state(Form.bot_desc)
    await message.answer("📝 <b>Enter Bot Description:</b>", parse_mode="HTML")

@router.message(Form.bot_desc)
async def process_bot_desc(message: Message, state: FSMContext):
    d = await state.get_data(); db.add_bot(d['bot_username'], d['bot_link'], message.text); await state.clear()
    await message.answer("✅ <b>Bot Added!</b>", parse_mode="HTML")

@router.callback_query(F.data == "admin_del_bot")
async def admin_del_bot(callback: CallbackQuery):
    bs = db.get_bots(); kb = []
    for b in bs: kb.append([InlineKeyboardButton(text=f"🗑 {b[1]}", callback_data=f"del_bot_{b[0]}")])
    await callback.message.answer("🗑 <b>Select Bot to Delete:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@router.callback_query(F.data.startswith("del_bot_"))
async def process_del_bot(callback: CallbackQuery):
    bid = int(callback.data.split("_")[2]); db.delete_bot(bid)
    await callback.message.answer("🗑 <b>Bot Deleted!</b>", parse_mode="HTML")

@router.callback_query(F.data == "admin_edit_bot")
async def admin_edit_bot(callback: CallbackQuery):
    bs = db.get_bots(); kb = []
    for b in bs: kb.append([InlineKeyboardButton(text=f"✏️ {b[1]}", callback_data=f"edit_bot_{b[0]}")])
    await callback.message.answer("✏️ <b>Select Bot to Edit:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@router.callback_query(F.data.startswith("edit_bot_"))
async def process_edit_bot_start(callback: CallbackQuery, state: FSMContext):
    bid = int(callback.data.split("_")[2]); await state.update_data(edit_bot_id=bid)
    await state.set_state(Form.edit_bot_username)
    await callback.message.answer("✏️ <b>Enter New Bot Username:</b>", parse_mode="HTML")

@router.message(Form.edit_bot_username)
async def process_edit_bot_username(message: Message, state: FSMContext):
    await state.update_data(edit_bot_username=message.text)
    await state.set_state(Form.edit_bot_link)
    await message.answer("🔗 <b>Enter New Bot Link:</b>", parse_mode="HTML")

@router.message(Form.edit_bot_link)
async def process_edit_bot_link(message: Message, state: FSMContext):
    await state.update_data(edit_bot_link=message.text)
    await state.set_state(Form.edit_bot_desc)
    await message.answer("📝 <b>Enter New Bot Description:</b>", parse_mode="HTML")

@router.message(Form.edit_bot_desc)
async def process_edit_bot_desc(message: Message, state: FSMContext):
    d = await state.get_data(); db.edit_bot(d['edit_bot_id'], d['edit_bot_username'], d['edit_bot_link'], message.text); await state.clear()
    await message.answer("✅ <b>Bot Updated!</b>", parse_mode="HTML")

@router.callback_query(F.data == "admin_add_api")
async def admin_add_api(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.api_title)
    await callback.message.answer("🔑 <b>Enter API Title:</b>", parse_mode="HTML")

@router.message(Form.api_title)
async def process_api_title(message: Message, state: FSMContext):
    await state.update_data(api_title=message.text)
    await state.set_state(Form.api_desc)
    await message.answer("📝 <b>Enter API Description:</b>", parse_mode="HTML")

@router.message(Form.api_desc)
async def process_api_desc(message: Message, state: FSMContext):
    d = await state.get_data(); db.add_api(d['api_title'], message.text); await state.clear()
    await message.answer("✅ <b>API Added!</b>", parse_mode="HTML")

@router.callback_query(F.data == "admin_del_api")
async def admin_del_api(callback: CallbackQuery):
    ap = db.get_apis(); kb = []
    for a in ap: kb.append([InlineKeyboardButton(text=f"🗑 {a[1]}", callback_data=f"del_api_{a[0]}")])
    await callback.message.answer("🗑 <b>Select API to Delete:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@router.callback_query(F.data.startswith("del_api_"))
async def process_del_api(callback: CallbackQuery):
    aid = int(callback.data.split("_")[2]); db.delete_api(aid)
    await callback.message.answer("🗑 <b>API Deleted!</b>", parse_mode="HTML")

@router.callback_query(F.data == "admin_edit_api")
async def admin_edit_api(callback: CallbackQuery):
    ap = db.get_apis(); kb = []
    for a in ap: kb.append([InlineKeyboardButton(text=f"✏️ {a[1]}", callback_data=f"edit_api_{a[0]}")])
    await callback.message.answer("✏️ <b>Select API to Edit:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@router.callback_query(F.data.startswith("edit_api_"))
async def process_edit_api_start(callback: CallbackQuery, state: FSMContext):
    aid = int(callback.data.split("_")[2]); await state.update_data(edit_api_id=aid)
    await state.set_state(Form.edit_api_title)
    await callback.message.answer("✏️ <b>Enter New API Title:</b>", parse_mode="HTML")

@router.message(Form.edit_api_title)
async def process_edit_api_title(message: Message, state: FSMContext):
    await state.update_data(edit_api_title=message.text)
    await state.set_state(Form.edit_api_desc)
    await message.answer("📝 <b>Enter New API Description:</b>", parse_mode="HTML")

@router.message(Form.edit_api_desc)
async def process_edit_api_desc(message: Message, state: FSMContext):
    d = await state.get_data(); db.edit_api(d['edit_api_id'], d['edit_api_title'], message.text); await state.clear()
    await message.answer("✅ <b>API Updated!</b>", parse_mode="HTML")

@router.callback_query(F.data == "admin_requests")
async def admin_requests(callback: CallbackQuery):
    rq = db.get_requests()
    if not rq: await callback.message.answer("📋 <b>No pending requests.</b>", parse_mode="HTML"); return
    for r in rq:
        u = db.get_user(r[1])
        t = f"""📋 <b>Group Request</b>

👤 <b>User:</b> {u[2] if u else 'Unknown'}
🔗 <b>Username:</b> @{u[1] if u and u[1] else 'N/A'}
🆔 <b>User ID:</b> <code>{r[1]}</code>
🔗 <b>Group Link:</b> {r[2]}
📝 <b>Reason:</b> {r[3]}"""
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Approve", callback_data=f"approve_req_{r[0]}"),
             InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_req_{r[0]}")]])
        await callback.message.answer(t, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("approve_req_"))
async def approve_request(callback: CallbackQuery):
    rid = int(callback.data.split("_")[2]); db.update_request(rid, "approved")
    conn = db.get_conn(); c = conn.cursor(); c.execute("SELECT user_id FROM requests WHERE id = ?", (rid,)); uid = c.fetchone()[0]; conn.close()
    await callback.message.answer("✅ <b>Request Approved!</b>", parse_mode="HTML")
    try: await bot.send_message(uid, "✅ <b>Your group request has been approved!</b>\n\nThe bot will be added to your group soon.", parse_mode="HTML")
    except: pass

@router.callback_query(F.data.startswith("reject_req_"))
async def reject_request(callback: CallbackQuery):
    rid = int(callback.data.split("_")[2]); db.update_request(rid, "rejected")
    conn = db.get_conn(); c = conn.cursor(); c.execute("SELECT user_id FROM requests WHERE id = ?", (rid,)); uid = c.fetchone()[0]; conn.close()
    await callback.message.answer("❌ <b>Request Rejected!</b>", parse_mode="HTML")
    try: await bot.send_message(uid, "❌ <b>Your group request has been rejected.</b>", parse_mode="HTML")
    except: pass

@router.callback_query(F.data == "admin_settings")
async def admin_settings(callback: CallbackQuery):
    s = db.get_settings()
    t = f"""⚙️ <b>Settings Panel</b>

🎁 <b>New User Credits:</b> {s['new_user_credit']}
🎁 <b>Referral Reward (User):</b> {s['referral_user_credit']}
🎁 <b>Referral Reward (Owner):</b> {s['referral_owner_credit']}
💳 <b>ZIP Cost:</b> {s['zip_cost']}
🔧 <b>Maintenance Mode:</b> {'ON' if s['maintenance_mode'] else 'OFF'}
📝 <b>Maintenance Message:</b> {s['maintenance_message']}"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 New User Credits", callback_data="set_new_user")],
        [InlineKeyboardButton(text="🎁 Referral User Reward", callback_data="set_ref_user")],
        [InlineKeyboardButton(text="🎁 Referral Owner Reward", callback_data="set_ref_owner")],
        [InlineKeyboardButton(text="💳 ZIP Cost", callback_data="set_zip_cost")],
        [InlineKeyboardButton(text="📝 Maintenance Message", callback_data="set_maint_msg")]])
    await callback.message.answer(t, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "set_new_user")
async def set_new_user(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.settings_new_user)
    await callback.message.answer("🎁 <b>Enter New User Credits:</b>", parse_mode="HTML")

@router.message(Form.settings_new_user)
async def process_set_new_user(message: Message, state: FSMContext):
    try: db.update_settings(new_user_credit=int(message.text)); await state.clear(); await message.answer("✅ <b>Setting Updated!</b>", parse_mode="HTML")
    except: await message.answer("❌ Invalid number."); await state.clear()

@router.callback_query(F.data == "set_ref_user")
async def set_ref_user(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.settings_ref_user)
    await callback.message.answer("🎁 <b>Enter Referral User Reward:</b>", parse_mode="HTML")

@router.message(Form.settings_ref_user)
async def process_set_ref_user(message: Message, state: FSMContext):
    try: db.update_settings(referral_user_credit=int(message.text)); await state.clear(); await message.answer("✅ <b>Setting Updated!</b>", parse_mode="HTML")
    except: await message.answer("❌ Invalid number."); await state.clear()

@router.callback_query(F.data == "set_ref_owner")
async def set_ref_owner(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.settings_ref_owner)
    await callback.message.answer("🎁 <b>Enter Referral Owner Reward:</b>", parse_mode="HTML")

@router.message(Form.settings_ref_owner)
async def process_set_ref_owner(message: Message, state: FSMContext):
    try: db.update_settings(referral_owner_credit=int(message.text)); await state.clear(); await message.answer("✅ <b>Setting Updated!</b>", parse_mode="HTML")
    except: await message.answer("❌ Invalid number."); await state.clear()

@router.callback_query(F.data == "set_zip_cost")
async def set_zip_cost(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.settings_zip_cost)
    await callback.message.answer("💳 <b>Enter ZIP Cost:</b>", parse_mode="HTML")

@router.message(Form.settings_zip_cost)
async def process_set_zip_cost(message: Message, state: FSMContext):
    try: db.update_settings(zip_cost=int(message.text)); await state.clear(); await message.answer("✅ <b>Setting Updated!</b>", parse_mode="HTML")
    except: await message.answer("❌ Invalid number."); await state.clear()

@router.callback_query(F.data == "set_maint_msg")
async def set_maint_msg(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.settings_maintenance_msg)
    await callback.message.answer("📝 <b>Enter Maintenance Message:</b>", parse_mode="HTML")

@router.message(Form.settings_maintenance_msg)
async def process_set_maint_msg(message: Message, state: FSMContext):
    db.update_settings(maintenance_message=message.text); await state.clear()
    await message.answer("✅ <b>Setting Updated!</b>", parse_mode="HTML")

@router.callback_query(F.data == "admin_add_credits")
async def admin_add_credits(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.add_credits_user); await state.update_data(action="add_credits")
    await callback.message.answer("➕ <b>Enter User ID to Add Credits:</b>", parse_mode="HTML")

@router.callback_query(F.data == "admin_remove_credits")
async def admin_remove_credits(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.remove_credits_user); await state.update_data(action="remove_credits")
    await callback.message.answer("➖ <b>Enter User ID to Remove Credits:</b>", parse_mode="HTML")

@router.message(Form.add_credits_user)
async def process_add_credits_user(message: Message, state: FSMContext):
    await state.update_data(target_user=message.text); await state.set_state(Form.add_credits_amount)
    await message.answer("➕ <b>Enter Amount of Credits to Add:</b>", parse_mode="HTML")

@router.message(Form.add_credits_amount)
async def process_add_credits_amount(message: Message, state: FSMContext):
    d = await state.get_data()
    try:
        uid = int(d['target_user']); amt = int(message.text); db.add_credits(uid, amt); await state.clear()
        await message.answer(f"✅ <b>Added {amt} credits to user {uid}</b>", parse_mode="HTML")
        try: await bot.send_message(uid, f"🎉 <b>{amt} credits have been added to your account!</b>", parse_mode="HTML")
        except: pass
    except: await message.answer("❌ Invalid input."); await state.clear()

@router.message(Form.remove_credits_user)
async def process_remove_credits_user(message: Message, state: FSMContext):
    await state.update_data(target_user=message.text); await state.set_state(Form.remove_credits_amount)
    await message.answer("➖ <b>Enter Amount of Credits to Remove:</b>", parse_mode="HTML")

@router.message(Form.remove_credits_amount)
async def process_remove_credits_amount(message: Message, state: FSMContext):
    d = await state.get_data()
    try:
        uid = int(d['target_user']); amt = int(message.text); db.remove_credits(uid, amt); await state.clear()
        await message.answer(f"✅ <b>Removed {amt} credits from user {uid}</b>", parse_mode="HTML")
    except: await message.answer("❌ Invalid input."); await state.clear()

@router.callback_query(F.data == "admin_zip_logs")
async def admin_zip_logs(callback: CallbackQuery):
    lg = db.get_zip_logs()
    if not lg: await callback.message.answer("📦 <b>No ZIP logs found.</b>", parse_mode="HTML"); return
    t = "📦 <b>Recent ZIP Logs</b>\n\n"
    for l in lg[:20]: t += f"👤 <b>User:</b> {l[1]}\n🌐 <b>URL:</b> {l[2]}\n📁 <b>Files:</b> {l[4]}\n📅 <b>Time:</b> {l[5]}\n\n"
    await callback.message.answer(t, parse_mode="HTML")

@router.callback_query(F.data == "admin_ref_logs")
async def admin_ref_logs(callback: CallbackQuery):
    lg = db.get_referral_logs()
    if not lg: await callback.message.answer("🔗 <b>No referral logs found.</b>", parse_mode="HTML"); return
    t = "🔗 <b>Referral Logs</b>\n\n"
    for l in lg: t += f"👤 <b>User ID:</b> {l[0]}\n🔗 <b>Code:</b> {l[1]}\n📊 <b>Count:</b> {l[2]}\n👤 <b>Referred By:</b> {l[3]}\n\n"
    await callback.message.answer(t, parse_mode="HTML")

@router.callback_query(F.data == "admin_premium_users")
async def admin_premium_users(callback: CallbackQuery):
    us = db.get_premium_users()
    if not us: await callback.message.answer("💎 <b>No premium users found.</b>", parse_mode="HTML"); return
    t = "💎 <b>Premium Users</b>\n\n"
    for u in us: t += f"👤 <b>User:</b> {u[2]}\n🆔 <b>ID:</b> <code>{u[0]}</code>\n💎 <b>Plan:</b> {u[11]}\n📅 <b>Expires:</b> {u[12]}\n\n"
    await callback.message.answer(t, parse_mode="HTML")

@router.callback_query(F.data == "admin_export_db")
async def admin_export_db(callback: CallbackQuery):
    if os.path.exists(DB_FILE):
        await callback.message.answer_document(FSInputFile(DB_FILE), caption="📤 <b>Database Export</b>", parse_mode="HTML")
    else: await callback.message.answer("❌ Database file not found.")

@router.callback_query(F.data == "admin_backup_db")
async def admin_backup_db(callback: CallbackQuery):
    bf = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"; shutil.copy(DB_FILE, bf)
    await callback.message.answer_document(FSInputFile(bf), caption="💾 <b>Database Backup</b>", parse_mode="HTML")
    os.remove(bf)

async def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())