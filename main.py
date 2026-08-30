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
    return "البوت المطور يعمل بنجاح ومستيقظ!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# جلب توكن البوت بأمان
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# مجلد مؤقت لحفظ الفيديوهات أثناء التحميل
DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

def extract_and_download_media(profile_url):
    ydl_opts = {
        'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s',  # صيغة اسم الملف المحمل
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',  # إجبار جلب MP4 حقيقي
        'playlist_items': '1-10',   # فحص آخر 10 منشورات
        'merge_output_format': 'mp4',
        'nocheckcertificate': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    }
    
    # 🍪 تفعيل الكوكيز للحسابات الخاصة
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'
        logger.info("🍪 تم تفعيل ملف Cookies.txt.")
        
    media_items = []
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            # جلب البيانات وتحميل الملفات فعلياً على السيرفر لتجاوز تعمية تويتر
            info = ydl.extract_info(profile_url, download=True)
            entries = info.get('entries', [info])
            
            for entry in entries:
                if not entry:
                    continue
                
                title = entry.get('title', 'ملف ميديا')
                # توقع المسار الذي تم حفظ ملف الفيديو فيه
                expected_filename = f"{DOWNLOAD_DIR}/{entry['id']}.mp4"
                
                # إذا تم تحميل الفيديو بنجاح كملف حقيقي
                if os.path.exists(expected_filename):
                    media_items.append({
                        "type": "فيديو 🎬",
                        "title": title,
                        "file_path": expected_filename,
                        "is_file": True
                    })
                # إذا كان المنشور عبارة عن صور فقط ولم يتم تحميل فيديو
                elif entry.get('thumbnails'):
                    best_image_url = entry['thumbnails'][-1]['url']
                    if 'twimg.com' in best_image_url and 'name=' in best_image_url:
                        best_image_url = best_image_url.split('&name=') + '&name=large'
                    media_items.append({
                        "type": "صورة 🖼️",
                        "title": title,
                        "url": best_image_url,
                        "is_file": False
                    })
                    
        except Exception as e:
            logger.error(f"حدث خطأ أثناء استخراج وتحميل الميديا: {e}")
            
    return media_items

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 أهلاً بك في البوت المطور! أرسل لي رابط حساب تويتر (X) أو رابط منشور، وسأقوم بتحميل الفيديوهات وإرسالها لك مباشرة كملفات قابلة للتشغيل.")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_url = update.message.text
    user_chat_id = update.message.chat_id
    
    if "twitter.com" in user_url or "x.com" in user_url:
        status_message = await update.message.reply_text("⏳ جاري تحميل الميديا وتجاوز الحظر، قد يستغرق الأمر لحظات...")
        
        media_items = extract_and_download_media(user_url)
        
        if media_items:
            await status_message.delete()  # حذف رسالة التحميل
            
            for index, item in enumerate(media_items, 1):
                try:
                    # إذا كانت المادة فيديو تم تحميله كملف
                    if item['is_file']:
                        with open(item['file_path'], 'rb') as video_file:
                            await context.bot.send_video(
                                chat_id=user_chat_id,
                                video=video_file,
                                caption=f"🎯 **المادة رقم {index}**\n📦 النوع: {item['type']}\n📝 العنوان: {item['title']}"
                            )
                        # حذف الملف فوراً من السيرفر بعد إرساله لتوفير المساحة
                        os.remove(item['file_path'])
                    
                    # إذا كانت المادة صورة (رابط مباشر)
                    else:
                        await context.bot.send_message(
                            chat_id=user_chat_id,
                            text=f"🎯 **المادة رقم {index}**\n📦 النوع: {item['type']}\n\n🔗 رابط الصورة المباشر:\n{item['url']}"
                        )
                except Exception as e:
                    logger.error(f"فشل إرسال المادة: {e}")
                    # الاحتياط لحذف الملف في حال فشل الإرسال
                    if item['is_file'] and os.path.exists(item['file_path']):
                        os.remove(item['file_path'])
                        
            await update.message.reply_text("🎉 تم تحميل وإرسال جميع المواد المتاحة بنجاح.")
        else:
            await status_message.edit_text("❌ لم يتم العثور على أي ميديا. تأكد من إعداد ملف cookies.txt إذا كان الحساب خاصاً.")
    else:
        await update.message.reply_text("⚠️ من فضلك أرسل رابط حساب تويتر (X) صحيح.")

def main():
    server_thread = Thread(target=run_web_server)
    server_thread.daemon = True
    server_thread.start()

    telegram_app = Application.builder().token(BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    
    logger.info("🤖 جاري تشغيل بوت التحميل المباشر...")
    telegram_app.run_polling()

if __name__ == '__main__':
    main()
                        
