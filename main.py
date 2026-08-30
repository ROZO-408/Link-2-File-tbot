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

def extract_all_media_links(profile_url):
    ydl_opts = {
        'extract_flat': False,      
        'skip_download': True,      # سحب روابط فقط بدون تحميل
        'playlist_items': '1-10',   # فحص آخر 10 منشورات
        # 🛠️ إجبار المحرك على تفضيل روابط الـ MP4 المباشرة وتجنب ملفات البث m3u8 التي تظهر كصورة غلاف
        'format': 'best[ext=mp4]/best',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    }
    
    # 🍪 إذا قمت برفع ملف كوكيز باسم cookies.txt بجانب الكود، سيستخدمه البوت لفتح الحسابات الخاصة
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'
        logger.info("🍪 تم العثور على ملف Cookies.txt وتفعيله لفتح الحسابات الخاصة.")
        
    media_links = []
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(profile_url, download=False)
            entries = info.get('entries', [info])
            
            for entry in entries:
                if not entry:
                    continue
                
                direct_video_url = None
                
                # فحص مصفوفة الصيغ (formats) لاستخراج روابط فيديو MP4 حقيقية مباشرة وموثوقة لـ تلجرام
                if entry.get('formats'):
                    mp4_formats = [
                        f for f in entry['formats'] 
                        if f.get('url') and (f.get('ext') == 'mp4' or 'mp4' in f.get('url').lower()) and not 'm3u8' in f.get('url').lower()
                    ]
                    if mp4_formats:
                        direct_video_url = mp4_formats[-1]['url'] # جلب أعلى جودة MP4 مباشرة
                
                # حل احتياطي إذا لم يجد تفاصيل الصيغ
                if not direct_video_url:
                    direct_video_url = entry.get('url')

                # التحقق الفعلي من طبيعة الرابط: هل هو فيديو حقيقي أم صورة؟
                is_video = entry.get('vcodec') != 'none' or 'video' in entry.get('extractor_key', '').lower() or (direct_video_url and 'mp4' in direct_video_url.lower())
                
                # 1. سحب روابط الفيديوهات المباشرة القابلة للتشغيل في تلجرام
                if direct_video_url and is_video:
                    media_links.append({"type": "فيديو 🎬", "url": direct_video_url})
                
                # 2. سحب الصور المصاحبة للمنشورات بأعلى دقة متوفرة (فقط إذا كان المنشور أصلاً صورة وليس فيديو)
                elif entry.get('thumbnails'):
                    best_image_url = entry['thumbnails'][-1]['url']
                    if 'twimg.com' in best_image_url and 'name=' in best_image_url:
                        best_image_url = best_image_url.split('&name=')[0] + '&name=large'
                    media_links.append({"type": "صورة 🖼️", "url": best_image_url})
                    
        except Exception as e:
            logger.error(f"حدث خطأ أثناء استخراج الميديا: {e}")
            
    return media_links

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 أهلاً بك في البوت المطور! أرسل لي رابط حساب تويتر (X) وسأقوم بسحب جميع الصور والفيديوهات المتاحة وإرسالها لك مباشرة.")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_url = update.message.text
    user_chat_id = update.message.chat_id
    
    if "twitter.com" in user_url or "x.com" in user_url:
        status_message = await update.message.reply_text("⏳ جاري اختراق القيود وفحص المنشورات وسحب الميديا الحقيقية...")
        
        media_items = extract_all_media_links(user_url)
        
        if media_items:
            await status_message.delete() # حذف رسالة جاري التحميل لتنظيف المحادثة وتسهيل العرض
            for index, item in enumerate(media_items, 1):
                try:
                    caption = f"🎯 **المادة رقم {index}**\n📦 النوع: {item['type']}\n\n🔗 رابط المصدر المباشر:\n{item['url']}"
                    await context.bot.send_message(chat_id=user_chat_id, text=caption)
                except Exception as e:
                    logger.error(f"فشل إرسال الرابط: {e}")
            await update.message.reply_text("🎉 تم إرسال جميع الصور والفيديوهات المتاحة بنجاح.")
        else:
            await status_message.edit_text("❌ لم يتم العثور على أي صور أو فيديوهات. تأكد من إعداد ملف cookies.txt إذا كان الحساب خاصاً.")
    else:
        await update.message.reply_text("⚠️ من فضلك أرسل رابط حساب تويتر (X) صحيح.")

def main():
    server_thread = Thread(target=run_web_server)
    server_thread.daemon = True
    server_thread.start()

    telegram_app = Application.builder().token(BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    
    logger.info("🤖 جاري تشغيل البوت المطور المباشر...")
    telegram_app.run_polling()

if __name__ == '__main__':
    main()
                  
