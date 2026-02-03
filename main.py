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

aktif_prosesler = {}  # hedef → {"proc": Popen, "baslangic_zamani": float}

# ================= KULLANICI VERİLERİ =================
def load_users():
    with open(KAYITLAR, "r") as f:
        data = json.load(f)
        for uid in data:
            if "toplam_sure_saniye" not in data[uid]:
                data[uid]["toplam_sure_saniye"] = 0
        return data

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
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "toplam_sure_saniye": 0
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

def en_cok_calisan_kullanici():
    data = load_users()
    if not data:
        return "Henüz kimse yok", "0 sn"

    en_iyi_uid, en_iyi_veri = max(
        data.items(),
        key=lambda x: x[1].get("toplam_sure_saniye", 0)
    )

    username = f"@{en_iyi_veri['username']}" if en_iyi_veri['username'] else f"ID:{en_iyi_uid}"
    toplam_s = en_iyi_veri["toplam_sure_saniye"]

    saat = toplam_s // 3600
    dk = (toplam_s % 3600) // 60
    sn = toplam_s % 60

    return username, f"{saat}s {dk}d {sn}sn"

# ================= BOT ÇALIŞTIRMA =================
def bot_calistir(hedef: str, filepath: str):
    logpath = os.path.join(LOG_DIR, f"{hedef}.txt")

    aktif_prosesler[hedef] = {
        "proc": None,
        "baslangic_zamani": time.time()
    }

    def run():
        while True:
            with open(logpath, "a", encoding="utf-8") as log:
                log.write(f"\n=== Başlatıldı {datetime.now()} ===\n")
                log.flush()

                try:
                    # requirements.txt varsa kur
                    req_path = os.path.join(os.path.dirname(filepath), "requirements.txt")
                    if os.path.exists(req_path):
                        log.write("requirements.txt bulundu → paketler kuruluyor...\n")
                        result = subprocess.run(
                            [sys.executable, "-m", "pip", "install", "-r", req_path],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            timeout=240
                        )
                        log.write(result.stdout + "\n")
                        if result.stderr:
                            log.write("HATA (pip):\n" + result.stderr + "\n")
                        log.write(f"pip return code: {result.returncode}\n")

                    # Botu çalıştır
                    log.write(f"python {filepath} başlatılıyor...\n")
                    proc = subprocess.Popen(
                        [sys.executable, filepath],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1
                    )
                    aktif_prosesler[hedef]["proc"] = proc

                    # Canlı log akışı
                    def stream_log(pipe, tag):
                        for line in iter(pipe.readline, ''):
                            log.write(f"{tag} {line.strip()}\n")
                            log.flush()

                    threading.Thread(target=stream_log, args=(proc.stdout, "[OUT]"), daemon=True).start()
                    threading.Thread(target=stream_log, args=(proc.stderr, "[ERR]"), daemon=True).start()

                    proc.wait()
                    log.write(f"Bot bitti (code: {proc.returncode})\n")

                except Exception as e:
                    log.write(f"ÇALIŞTIRMA HATASI: {type(e).__name__}: {str(e)}\n")
                finally:
                    log.flush()
                    time.sleep(5)

    threading.Thread(target=run, daemon=True).start()

# ================= START MESAJI (tam senin istediğin format) =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    sira, toplam = kullanici_ekle(user, context)

    username_display = f"@{user.username}" if user.username else f"ID:{user.id}"
    birinci, sure = en_cok_calisan_kullanici()

    mesaj = f"""Bu Botta Sıra #{sira}.sin {username_display}

İyi Kullanımlar🥳

🏆 Birinci: {birinci} ({sure})

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

# ================= DİĞER KOMUTLAR (kısaca) =================
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    hedef = str(user.username or user.id)

    doc = update.message.document
    if not doc or not doc.file_name.lower().endswith(".py"):
        await update.message.reply_text("Sadece .py dosyası kabul ediyorum")
        return

    filename = f"{hedef}_{doc.file_name}"
    path = os.path.join(UPLOAD_DIR, filename)

    file = await doc.get_file()
    await file.download_to_drive(path)

    bot_calistir(hedef, path)
    await update.message.reply_text(f"✅ {doc.file_name} yüklendi ve başlatıldı\nLog: /log")

async def aktifet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    hedef = str(user.username or user.id)

    dosyalar = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(hedef + "_") and f.endswith(".py")]
    if not dosyalar:
        await update.message.reply_text("Hiç .py dosyan yok")
        return

    en_yeni = max(dosyalar, key=lambda f: os.path.getmtime(os.path.join(UPLOAD_DIR, f)))
    path = os.path.join(UPLOAD_DIR, en_yeni)

    bot_calistir(hedef, path)
    await update.message.reply_text("🚀 En son dosya çalıştırıldı\nLog: /log")

async def kapat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hedef = str(update.effective_user.username or update.effective_user.id)

    if hedef not in aktif_prosesler:
        await update.message.reply_text("Bot zaten kapalı")
        return

    info = aktif_prosesler[hedef]
    proc = info.get("proc")
    baslangic = info.get("baslangic_zamani", 0)

    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except:
            proc.kill()

        gecen = int(time.time() - baslangic)
        data = load_users()
        uid = hedef
        if uid in data:
            data[uid]["toplam_sure_saniye"] = data[uid].get("toplam_sure_saniye", 0) + gecen
            save_users(data)

        del aktif_prosesler[hedef]
        await update.message.reply_text("🛑 Bot durduruldu")
    else:
        await update.message.reply_text("Bot zaten kapalı")

async def durum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hedef = str(update.effective_user.username or update.effective_user.id)
    if hedef in aktif_prosesler and aktif_prosesler[hedef].get("proc") and aktif_prosesler[hedef]["proc"].poll() is None:
        await update.message.reply_text("🟢 Bot aktif")
    else:
        await update.message.reply_text("🔴 Bot çalışmıyor")

async def log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("Yetkisiz")
    hedef = context.args[0].lstrip("@") if context.args else str(update.effective_user.username or update.effective_user.id)
    logf = os.path.join(LOG_DIR, f"{hedef}.txt")
    if not os.path.exists(logf):
        return await update.message.reply_text("Log dosyası yok")
    with open(logf, "r", encoding="utf-8") as f:
        txt = f.read()[-4000:]
    await update.message.reply_text(f"```\n{txt}\n```", parse_mode="Markdown")

# ... diğer komutlar (liste vs.) aynı kalabilir

# ================= WEBHOOK SETUP (önceki stabil hali) =================
# (buraya önceki mesajdaki webhook main fonksiyonunu koyabilirsin, değişmedi)

async def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("aktifet", aktifet))
    application.add_handler(CommandHandler("kapat", kapat))
    application.add_handler(CommandHandler("durum", durum))
    application.add_handler(CommandHandler("log", log))
    # application.add_handler(CommandHandler("liste", liste))  # varsa ekle

    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # webhook kısmı önceki mesajdaki gibi (set_webhook_with_retry vs.)

    # ... (webhook başlatma kodunu buraya yapıştır)

if __name__ == "__main__":
    asyncio.run(main()).url == webhook_url:
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
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
