# ================= TEMEL =================
import os, sys, json, time, asyncio, subprocess, threading, signal
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, ContextTypes, filters
)
from telegram.error import RetryAfter

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise SystemExit("BOT_TOKEN eksik")

ADMIN_ID = 8444268448  # ❗ İLK KODDAN AYNEN ALINDI

UPLOAD_DIR = "gelen_dosyalar"
LOG_DIR = "loglar"
USERS_FILE = "kullanicilar.json"
BAN_FILE = "banli.json"

MAX_SURE = 3600        # 1 saat
MAX_RESTART = 3

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

for f in [USERS_FILE, BAN_FILE]:
    if not os.path.exists(f):
        json.dump({}, open(f, "w"))

aktif_prosesler = {}

# ================= JSON =================
def load(p): return json.load(open(p))
def save(p, d): json.dump(d, open(p, "w"), indent=2, ensure_ascii=False)

# ================= USER =================
def user_add(user):
    d = load(USERS_FILE)
    uid = str(user.id)
    if uid not in d:
        d[uid] = {
            "username": user.username,
            "toplam": 0,
            "kayit": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        save(USERS_FILE, d)

def banli(uid):
    return str(uid) in load(BAN_FILE)

# ================= BOT ÇALIŞTIR =================
def run_bot(owner, path):
    if owner in aktif_prosesler:
        return False

    logpath = f"{LOG_DIR}/{owner}.txt"
    restarts = 0

    def runner():
        nonlocal restarts
        while restarts < MAX_RESTART:
            start = time.time()
            with open(logpath, "a", encoding="utf-8") as log:
                log.write(f"\n[{datetime.now()}] BAŞLADI\n")

                try:
                    req = os.path.join(os.path.dirname(path), "requirements.txt")
                    if os.path.exists(req):
                        subprocess.run(
                            [sys.executable, "-m", "pip", "install", "-r", req],
                            stdout=log, stderr=log
                        )

                    proc = subprocess.Popen(
                        [sys.executable, path],
                        stdout=log, stderr=log
                    )

                    aktif_prosesler[owner] = {
                        "proc": proc,
                        "start": start
                    }

                    while proc.poll() is None:
                        if time.time() - start > MAX_SURE:
                            proc.terminate()
                            log.write("⏱ Süre doldu\n")
                            break
                        time.sleep(2)

                    log.write(f"ÇIKIŞ KODU: {proc.returncode}\n")

                except Exception as e:
                    log.write(f"HATA: {e}\n")

            restarts += 1
            time.sleep(5)

        aktif_prosesler.pop(owner, None)

    threading.Thread(target=runner, daemon=True).start()
    return True

# ================= KOMUTLAR =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if banli(user.id):
        return

    user_add(user)

    mesaj = f"""Bu Botta Sıra #{user.id}

İyi Kullanımlar🥳

Nasıl Kullanır❓
🚀 .py Bot Alt Yapınızı Gönderin.
🚀 Eksik paketler otomatik kurulacak ve bot çalışacak.

📜Komutlar : 
/aktifet → Botunu Aktif Et 🟢
/kapat → Botunu Durdur 🔴
/durum → Botun Durumu ℹ️
/log @kullanici → Başkasının Logu (Admin) 🕸️
/liste → Üyeler (Admin) 👤

✈️Telegram : bot sahibi @zordodestek | yetkili @mutluapk ✈️"""

    await update.message.reply_text(mesaj)

async def upload(update: Update, context):
    user = update.effective_user
    if banli(user.id):
        return

    doc = update.message.document
    if not doc or not doc.file_name.endswith(".py"):
        return await update.message.reply_text("❌ Sadece .py")

    owner = str(user.id)
    path = f"{UPLOAD_DIR}/{owner}_{doc.file_name}"
    await (await doc.get_file()).download_to_drive(path)

    ok = run_bot(owner, path)
    await update.message.reply_text("✅ Çalıştırıldı" if ok else "⚠️ Zaten aktif botun var")

async def aktifet(update: Update, context):
    owner = str(update.effective_user.id)
    if owner in aktif_prosesler:
        return await update.message.reply_text("🟢 Zaten aktif")

    files = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(owner)]
    if not files:
        return await update.message.reply_text("Dosya yok")

    run_bot(owner, f"{UPLOAD_DIR}/{files[-1]}")
    await update.message.reply_text("🚀 Aktif edildi")

async def kapat(update: Update, context):
    owner = str(update.effective_user.id)
    if owner not in aktif_prosesler:
        return await update.message.reply_text("Zaten kapalı")

    p = aktif_prosesler[owner]["proc"]
    p.terminate()

    sure = int(time.time() - aktif_prosesler[owner]["start"])
    users = load(USERS_FILE)
    users[owner]["toplam"] += sure
    save(USERS_FILE, users)

    aktif_prosesler.pop(owner, None)
    await update.message.reply_text("🛑 Bot durduruldu")

async def durum(update: Update, context):
    owner = str(update.effective_user.id)
    await update.message.reply_text("🟢 Aktif" if owner in aktif_prosesler else "🔴 Kapalı")

async def log(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        return

    hedef = context.args[0].lstrip("@") if context.args else str(update.effective_user.id)
    lf = f"{LOG_DIR}/{hedef}.txt"
    if not os.path.exists(lf):
        return await update.message.reply_text("Log yok")

    txt = open(lf, encoding="utf-8").read()[-4000:]
    await update.message.reply_text(f"```\n{txt}\n```", parse_mode="Markdown")

async def liste(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    users = load(USERS_FILE)
    msg = "👤 Kullanıcılar:\n"
    for u in users:
        msg += f"- {u}\n"
    await update.message.reply_text(msg)

# ================= MAIN =================
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("aktifet", aktifet))
    app.add_handler(CommandHandler("kapat", kapat))
    app.add_handler(CommandHandler("durum", durum))
    app.add_handler(CommandHandler("log", log))
    app.add_handler(CommandHandler("liste", liste))
    app.add_handler(MessageHandler(filters.Document.ALL, upload))

    await app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        webhook_url=f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}"
    )

if __name__ == "__main__":
    asyncio.run(main())
