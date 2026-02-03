import os
import sys
import json
import subprocess
import threading
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, filters, ContextTypes
)

# ================= AYARLAR =================
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = 8444268448

UPLOAD_DIR = "gelen_dosyalar"
LOG_DIR = "loglar"
KAYITLAR = "kullanicilar.json"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

if not os.path.exists(KAYITLAR):
    with open(KAYITLAR, "w") as f:
        json.dump({}, f)

aktif_prosesler = {}

# ================= KULLANICI =================
def load_users():
    with open(KAYITLAR, "r") as f:
        return json.load(f)

def save_users(data):
    with open(KAYITLAR, "w") as f:
        json.dump(data, f, indent=2)

def kullanici_ekle(user, context=None):
    data = load_users()
    uid = str(user.id)

    if uid not in data:
        data[uid] = {
            "username": user.username,
            "sira": len(data) + 1,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_users(data)

        if context:
            context.bot.send_message(
                ADMIN_ID,
                f"🆕 Yeni Kullanıcı\n"
                f"👤 @{user.username or user.id}\n"
                f"📊 Toplam Kullanıcı: {len(data)}"
            )

    return data[uid]["sira"], len(data)

# ================= BOT ÇALIŞTIR =================
def bot_calistir(hedef, filepath):
    logpath = os.path.join(LOG_DIR, f"{hedef}.txt")

    def run():
        while True:
            with open(logpath, "a") as log:
                log.write(f"\n=== Başlatıldı {datetime.now()} ===\n")
                try:
                    req = os.path.join(os.path.dirname(filepath), "requirements.txt")
                    if os.path.exists(req):
                        subprocess.run(
                            [sys.executable, "-m", "pip", "install", "-r", req],
                            stdout=log, stderr=log
                        )

                    proc = subprocess.Popen(
                        [sys.executable, filepath],
                        stdout=log,
                        stderr=log
                    )
                    aktif_prosesler[hedef] = proc
                    proc.wait()
                except Exception as e:
                    log.write(f"HATA: {e}\n")

    threading.Thread(target=run, daemon=True).start()

# ================= KOMUTLAR =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    sira, toplam = kullanici_ekle(user, context)

    await update.message.reply_text(
        f"ZORDO Vds Botuna Hosgeldin 🖥️\n"
        f"@{user.username or user.id}!\n"
        f"Bu Botta Sıra #{sira}.sin\n\n"
        f"👥 Toplam Kullanıcı: {toplam}\n\n"
        "Nasıl Kullanır❓\n"
        "🚀 .py Bot Alt Yapısını Gönder\n"
        "🚀 Paketler otomatik kurulur\n\n"
        "📜Komutlar:\n"
        "/aktifet → Botunu Aktif Et 🟢\n"
        "/kapat → Botunu Durdur 🔴\n"
        "/durum → Botun Durumu ℹ️\n"
        "/log @kullanici → Log (Admin)\n"
        "/liste → Üyeler (Admin)\n\n"
        "✈️ Telegram :bot sahibi @zordodestek |  yetkili @mutluapk"
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    hedef = str(user.username or user.id)

    doc = update.message.document
    if not doc.file_name.endswith(".py"):
        return await update.message.reply_text("⚠️ Sadece .py dosyası")

    filename = f"{hedef}_{doc.file_name}"
    path = os.path.join(UPLOAD_DIR, filename)

    file = await context.bot.get_file(doc.file_id)
    await file.download_to_drive(path)

    bot_calistir(hedef, path)

    await update.message.reply_text("✅ Bot aktif edildi")

async def aktifet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    hedef = str(user.username or user.id)

    dosyalar = sorted(
        [f for f in os.listdir(UPLOAD_DIR) if f.startswith(hedef + "_")],
        reverse=True
    )

    if not dosyalar:
        return await update.message.reply_text("Dosya bulunamadı")

    bot_calistir(hedef, os.path.join(UPLOAD_DIR, dosyalar[0]))
    await update.message.reply_text("🚀 Bot çalıştırıldı")

async def kapat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hedef = str(update.effective_user.username or update.effective_user.id)
    proc = aktif_prosesler.get(hedef)

    if proc and proc.poll() is None:
        proc.terminate()
        await update.message.reply_text("🛑 Bot durduruldu")
    else:
        await update.message.reply_text("Bot zaten kapalı")

async def durum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hedef = str(update.effective_user.username or update.effective_user.id)
    proc = aktif_prosesler.get(hedef)

    if proc and proc.poll() is None:
        await update.message.reply_text("🟢 Bot aktif")
    else:
        await update.message.reply_text("🔴 Bot çalışmıyor")

async def log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    hedef = str(user.username or user.id)

    if context.args and user.id == ADMIN_ID:
        hedef = context.args[0].lstrip("@")

    logf = os.path.join(LOG_DIR, f"{hedef}.txt")
    if not os.path.exists(logf):
        return await update.message.reply_text("Log yok")

    with open(logf, "r") as f:
        txt = f.read()[-1200:]

    await update.message.reply_text(f"```\n{txt}\n```", parse_mode="Markdown")

async def liste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    data = load_users()
    msg = "👥 Üyeler\n\n"

    for uid, v in data.items():
        msg += f"#{v['sira']} → @{v['username'] or uid}\n"

    await update.message.reply_text(msg)

# ================= WEBHOOK SETUP =================
async def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("aktifet", aktifet))
    application.add_handler(CommandHandler("kapat", kapat))
    application.add_handler(CommandHandler("durum", durum))
    application.add_handler(CommandHandler("log", log))
    application.add_handler(CommandHandler("liste", liste))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Render'dan gelen PORT'u al (genelde 10000 olur)
    port = int(os.environ.get("PORT", "8443"))

    # Render'ın sana verdiği domain (otomatik environment variable)
    # Örnek: https://zordo-bot.onrender.com
    external_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    if not external_hostname:
        print("UYARI: RENDER_EXTERNAL_HOSTNAME environment variable bulunamadı!")
        return

    webhook_url = f"https://{external_hostname}/{TOKEN}"

    await application.initialize()
    await application.start()

    await application.bot.set_webhook(
        url=webhook_url,
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True  # deploy sonrası biriken mesajları at
    )

    print(f"🚀 Webhook ayarlandı: {webhook_url}")
    print("Render Web Service olarak çalışıyor – polling kullanılmıyor")

    # Webhook sunucusunu başlat (python-telegram-bot kendi tornado sunucusunu kullanır)
    await application.updater.start_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=TOKEN,               # güvenlik için token'ı path'e koyduk
        webhook_url=webhook_url
    )

    # Botu sonsuza kadar çalıştır
    await application.updater.wait_for_stop()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
