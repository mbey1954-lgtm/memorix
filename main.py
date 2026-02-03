import os
import sys
import json
import subprocess
import threading
import asyncio
import time
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, filters, ContextTypes,
    Application
)
from telegram.error import RetryAfter, TelegramError

# ================= AYARLAR =================
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN environment variable eksik! Render'da ekle.")

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

def kullanici_ekle(user, context: ContextTypes.DEFAULT_TYPE = None):
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
            asyncio.create_task(context.bot.send_message(
                ADMIN_ID,
                f"🆕 Yeni Kullanıcı\n"
                f"👤 @{user.username or user.id}\n"
                f"📊 Toplam Kullanıcı: {len(data)}"
            ))

    return data[uid]["sira"], len(data)

# ================= BOT ÇALIŞTIR =================
def bot_calistir(hedef: str, filepath: str):
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
                    log.write(f"HATA: {str(e)}\n")
                    log.flush()
                    time.sleep(10)  # hata sonrası kısa bekle

    threading.Thread(target=run, daemon=True).start()

# ================= KOMUTLAR =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    sira, toplam = kullanici_ekle(user, context)
    await update.message.reply_text(
        f"ZORDO Vds Botuna Hoşgeldin 🖥️\n"
        f"@{user.username or user.id}!\n"
        f"Sıra: #{sira} / Toplam: {toplam}\n\n"
        "Nasıl Kullanılır?\n"
        "→ .py dosyasını buraya gönder\n"
        "→ Paketler otomatik kurulur\n\n"
        "Komutlar:\n"
        "/aktifet → Botu çalıştır\n"
        "/kapat → Durdur\n"
        "/durum → Durum kontrol\n"
        "/log → Logları gör (admin)\n"
        "/liste → Kullanıcı listesi (admin)"
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    hedef = str(user.username or user.id)

    doc = update.message.document
    if not doc or not doc.file_name.lower().endswith(".py"):
        await update.message.reply_text("⚠️ Sadece .py dosyası kabul ediyorum")
        return

    filename = f"{hedef}_{doc.file_name}"
    path = os.path.join(UPLOAD_DIR, filename)

    file = await doc.get_file()
    await file.download_to_drive(path)

    bot_calistir(hedef, path)
    await update.message.reply_text(f"✅ {doc.file_name} yüklendi ve çalıştırıldı")

async def aktifet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    hedef = str(user.username or user.id)

    dosyalar = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(hedef + "_") and f.endswith(".py")]
    if not dosyalar:
        await update.message.reply_text("❌ Hiç .py dosyan yok")
        return

    en_yeni = max(dosyalar, key=lambda f: os.path.getmtime(os.path.join(UPLOAD_DIR, f)))
    path = os.path.join(UPLOAD_DIR, en_yeni)

    bot_calistir(hedef, path)
    await update.message.reply_text("🚀 En son dosya çalıştırıldı")

async def kapat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hedef = str(update.effective_user.username or update.effective_user.id)
    proc = aktif_prosesler.get(hedef)
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except:
            proc.kill()
        await update.message.reply_text("🛑 Bot durduruldu")
    else:
        await update.message.reply_text("Bot zaten kapalı")

async def durum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hedef = str(update.effective_user.username or update.effective_user.id)
    proc = aktif_prosesler.get(hedef)
    durum_text = "🟢 Aktif" if proc and proc.poll() is None else "🔴 Kapalı"
    await update.message.reply_text(f"Durum: {durum_text}")

# log ve liste komutlarını basit tuttum, istersen genişletebilirsin

async def log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("Yetkisiz")
    hedef = context.args[0].lstrip("@") if context.args else str(update.effective_user.username or update.effective_user.id)
    logf = os.path.join(LOG_DIR, f"{hedef}.txt")
    if not os.path.exists(logf):
        return await update.message.reply_text("Log dosyası yok")
    with open(logf, "r") as f:
        txt = f.read()[-2000:]
    await update.message.reply_text(f"```\n{txt}\n```", parse_mode="Markdown")

async def liste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    data = load_users()
    msg = "Kullanıcılar:\n"
    for uid, v in sorted(data.items(), key=lambda x: x[1]["sira"]):
        msg += f"#{v['sira']} - @{v['username'] or uid} ({v['time']})\n"
    await update.message.reply_text(msg or "Henüz kullanıcı yok")

# ================= WEBHOOK SETUP =================
async def set_webhook_with_retry(bot, webhook_url, max_retries=4):
    for attempt in range(1, max_retries + 1):
        try:
            await bot.set_webhook(
                url=webhook_url,
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )
            return True
        except RetryAfter as e:
            print(f"Flood → {e.retry_after} sn bekleniyor (deneme {attempt})")
            await asyncio.sleep(e.retry_after + 1.5)
        except TelegramError as e:
            print(f"Webhook hatası: {e}")
            await asyncio.sleep(3)
    print("Webhook set edilemedi – max deneme aşıldı")
    return False

async def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("aktifet", aktifet))
    application.add_handler(CommandHandler("kapat", kapat))
    application.add_handler(CommandHandler("durum", durum))
    application.add_handler(CommandHandler("log", log))
    application.add_handler(CommandHandler("liste", liste))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    port = int(os.environ.get("PORT", 8443))
    hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    if not hostname:
        print("HATA: RENDER_EXTERNAL_HOSTNAME yok – Render Web Service mi?")
        return

    webhook_path = f"/{TOKEN}"
    webhook_url = f"https://{hostname}{webhook_path}"

    print(f"Webhook hedef URL: {webhook_url}")
    print(f"Port: {port}")

    await application.initialize()
    await application.start()

    # Mevcut webhook kontrolü – flood'u önler
    try:
        current = await application.bot.get_webhook_info()
        if current.url == webhook_url:
            print("Webhook zaten doğru ayarlı – tekrar set ETMEYİ atlıyoruz")
        else:
            print("Webhook farklı / yok → set ediliyor...")
            success = await set_webhook_with_retry(application.bot, webhook_url)
            if success:
                print("Webhook başarıyla ayarlandı!")
            else:
                print("Webhook ayarlanamadı – logları kontrol et")
    except Exception as e:
        print(f"Webhook kontrol/set hatası: {e}")

    await application.updater.start_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=webhook_path,
        webhook_url=webhook_url,
        drop_pending_updates=True
    )

    print("Webhook sunucusu başladı – Render'da hazır")
    await asyncio.Event().wait()  # Botu açık tut

if __name__ == "__main__":
    asyncio.run(main())
