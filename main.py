import os
import logging
from threading import Thread
from flask import Flask
import yt_dlp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# إعدادات تسجيل الأخطاء (Logging)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask('')

@app.route('/')
def home():
    return "البوت العالمي يعمل بنجاح ومستيقظ!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# جلب توكن البوت بأمان من إعدادات Render
BOT_TOKEN = os.environ.get("BOT_TOKEN")

def extract_universal_media(url):
    """
    دالة عالمية تعتمد على yt-dlp لفحص أي رابط (فيديو، صورة، حساب، قائمة تشغيل)
    وتستخرج الروابط المباشرة للميديا دون تحميل الملفات على السيرفر.
    """
    ydl_opts = {
        'extract_flat': False,      # نحتاج فحص المحتوى بالكامل لاستخراج الروابط المباشرة
        'skip_download': True,      # 🚫 منع التحميل لتوفير مساحة السيرفر وسرعة الاستجابة
        'playlist_items': '1-10',   # إذا كان الرابط لحساب أو قائمة، يسحب آخر 10 مواد فقط لتفادي الحظر
    }
    
    # 🍪 تفعيل ملف الكوكيز تلقائياً إذا قمت برفعه لفك الحسابات الخاصة والمقيدة
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'
        logger.info("🍪 تم استخدام ملف cookies.txt لتخطي الحظر والقيود.")

    media_list = []
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            
            # إذا كان الرابط يحتوي على مدخلات متعددة (حساب، قائمة تشغيل، أو منشور متعدد الصور)
            entries = info.get('entries', [info])
            
            for entry in entries:
                if not entry:
                    continue
                
                title = entry.get('title', 'ميديا بدون عنوان')
                
                # 1. التحقق إذا كان الرابط المستخرج عبارة عن فيديو أو مقطع صوتي
                # بعض المواقع تقدم الرابط المباشر في حقل 'url' والبعض في مصفوفة 'formats'
                direct_url = entry.get('url')
                is_video = entry.get('vcodec') != 'none' or 'video' in entry.get('extractor_key', '').lower()
                
                if direct_url and (is_video or entry.get('acodec') != 'none'):
                    media_list.append({
                        "type": "🎥 فيديو / صوت مباشر",
                        "title": title,
                        "url": direct_url
                    })
                
                # 2. إذا لم يكن فيديو، نتحقق من وجود صور أصلية أو غلاف بدقة عالية (مثل صور تويتر وإنستغرام)
                elif entry.get('thumbnails'):
                    # جلب أفضل وأكبر دقة صورة متاحة في القائمة
                    best_thumbnail = entry['thumbnails'][-1]['url']
                    
                    # تحسين دقة صور تويتر (X) إن وجدت
                    if 'twimg.com' in best_thumbnail and 'name=' in best_thumbnail:
                        best_thumbnail = best_thumbnail.split('&name=')[0] + '&name=large'
                        
                    media_list.append({
                        "type": "🖼️ صورة بدقة عالية",
                        "title": title,
                        "url": best_thumbnail
                    })
                    
        except Exception as e:
            logger.error(f"حدث خطأ أثناء فحص الرابط عبر yt-dlp: {e}")
            
    return media_list

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلاً بك في البوت العالمي الشامل!\n\n"
        "🚀 يمكنك إرسال أي رابط الآن (حساب تويتر، فيديو يوتيوب، مقطع تيك توك، إنستغرام، فيسبوك... إلخ).\n"
        "🎯 سأقوم فوراً باستخراج الروابط المباشرة للميديا (فيديوهات أو صور) وإرسالها لك هنا في الخاص مجاناً!"
    )

async def handle_any_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_url = update.message.text
    user_chat_id = update.message.chat_id
    
    # تعبير نمطي بسيط للتأكد أن النص المرسل هو رابط ويب (URL) فعلي
    if user_url.startswith("http://") or user_url.startswith("https://"):
        status_message = await update.message.reply_text("⏳ جاري تحليل الرابط عبر محرك yt-dlp واستخراج الميديا المباشرة...")
        
        # استدعاء الدالة العالمية لفحص الرابط
        found_media = extract_universal_media(user_url)
        
        if found_media:
            await status_message.edit_text(f"✅ تم العثور على {len(found_media)} ملف ميديا. جاري إرسال الروابط لك...")
            
            for index, item in enumerate(found_media, 1):
                try:
                    caption = (
                        f"🎯 **المادة رقم {index}**\n"
                        f"📦 النوع: {item['type']}\n"
                        f"📝 العنوان: {item['title']}\n\n"
                        f"🔗 الرابط المباشر:\n{item['url']}"
                    )
                    # إرسال البيانات للمستخدم مباشرة في الخاص
                    await context.bot.send_message(chat_id=user_chat_id, text=caption, parse_mode="Markdown")
                except Exception as e:
                    logger.error(f"فشل إرسال رسالة الميديا: {e}")
                    
            await update.message.reply_text("🎉 تم استخراج وإرسال جميع الروابط المتاحة بنجاح!")
        else:
            await status_message.edit_text("❌ عذراً، لم نتمكن من استخراج ميديا مباشرة من هذا الرابط. قد يكون الموقع بحاجة لتحديث المحرك أو الحساب خاص جداً.")
    else:
        await update.message.reply_text("⚠️ من فضلك أرسل رابط ويب صحيح يبدأ بـ http أو https.")

def main():
    # تشغيل خادم الويب في الخلفية من أجل إبقاء منصة Render مستيقظة
    server_thread = Thread(target=run_web_server)
    server_thread.daemon = True
    server_thread.start()

    # تشغيل بوت التلجرام بالتوكن الخاص بك
    telegram_app = Application.builder().token(BOT_TOKEN).build()
    
    # معالجة الأوامر والرسائل
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_any_link))
    
    logger.info("🤖 البوت العالمي مستعد لاستقبال أي رابط...")
    telegram_app.run_polling()

if __name__ == '__main__':
    main()
