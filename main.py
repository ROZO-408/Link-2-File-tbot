import os
import logging
from threading import Thread
from flask import Flask
import yt_dlp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# تسجيل الأخطاء
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask('')

@app.route('/')
def home():
    return "البوت يعمل بنجاح ومستيقظ!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# جلب توكن البوت بأمان من إعدادات Render
BOT_TOKEN = os.environ.get("BOT_TOKEN")

def extract_video_direct_links(profile_url):
    ydl_opts = {
        'extract_flat': False,      
        'skip_download': True,      # 🚫 منع تحميل الملف على السيرفر (سحب روابط فقط)
        'playlist_items': '1-10',   # سحب آخر 10 منشورات فقط لتفادي الحظر
    }
    direct_links = []
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(profile_url, download=False)
            if 'entries' in info:
                for entry in info['entries']:
                    if entry and 'url' in entry:
                        direct_links.append(entry['url'])
            else:
                if 'url' in info:
                    direct_links.append(info['url'])
        except Exception as e:
            logger.error(f"حدث خطأ أثناء استخراج الروابط: {e}")
            
    return direct_links

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 أهلاً بك! أرسل لي رابط حساب تويتر (X) وسأقوم بسحب روابط الفيديوهات وإرسالها لك هنا مباشرة في الخاص.")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_url = update.message.text
    # جلب معرف الشات الخاص بالمستخدم تلقائياً للإرسال له في الخاص
    user_chat_id = update.message.chat_id
    
    if "twitter.com" in user_url or "x.com" in user_url:
        status_message = await update.message.reply_text("⏳ جاري فحص الحساب واستخراج روابط الفيديوهات المباشرة...")
        video_links = extract_video_direct_links(user_url)
        
        if video_links:
            await status_message.edit_text(f"✅ تم العثور على {len(video_links)} رابط فيديو. جاري إرسالهم لك...")
            for index, link in enumerate(video_links, 1):
                try:
                    caption = f"🎬 رابط الفيديو المباشر رقم {index}:\n\n{link}"
                    await context.bot.send_message(chat_id=user_chat_id, text=caption)
                except Exception as e:
                    logger.error(f"فشل إرسال الرابط: {e}")
            await update.message.reply_text("🎉 تم إرسال جميع الروابط بنجاح.")
        else:
            await status_message.edit_text("❌ لم يتم العثور على فيديوهات أو الحساب خاص ومقيد.")
    else:
        await update.message.reply_text("⚠️ من فضلك أرسل رابط حساب تويتر (X) صحيح.")

def main():
    server_thread = Thread(target=run_web_server)
    server_thread.daemon = True
    server_thread.start()

    telegram_app = Application.builder().token(BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    
    logger.info("🤖 جاري تشغيل البوت المباشر...")
    telegram_app.run_polling()

if __name__ == '__main__':
    main()
