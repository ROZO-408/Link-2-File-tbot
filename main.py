import os
import logging
import cv2  # مكتبة OpenCV لجلب أبعاد الفيديو وتوليد الصورة المصغرة تلقائياً
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
    return "بوت التحميل الفوري المطور يعمل!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# جلب توكن البوت بأمان
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# مجلد مؤقت لحفظ الفيديوهات والصور المصغرة
DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

def get_video_meta_and_thumb(video_path):
    """
    دالة تقوم بفتح الفيديو، جلب أبعاده (العرض والارتفاع)،
    وتوليد صورة مصغرة (Thumbnail) من أول إطار لجعل تلجرام يدعم التشغيل الفوري.
    """
    width, height, duration = 0, 0, 0
    thumb_path = video_path + "_thumb.jpg"
    
    try:
        cap = cv2.VideoCapture(video_path)
        if cap.isOpened():
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if fps > 0:
                duration = int(frame_count / fps)
            
            # قراءة الإطار الأول لحفظه كصورة مصغرة
            ret, frame = cap.read()
            if ret:
                cv2.imwrite(thumb_path, frame)
        cap.release()
    except Exception as e:
        logger.error(f"خطأ أثناء جلب أبعاد الفيديو: {e}")
        
    return width, height, duration, thumb_path if os.path.exists(thumb_path) else None

def extract_and_download_media(profile_url):
    ydl_opts = {
        'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s',
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',  
        'playlist_items': '1-10',   
        'nocheckcertificate': True,
        'merge_output_format': 'mp4',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    }
    
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'
        
    media_items = []
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(profile_url, download=True)
            entries = info.get('entries', [info])
            
            for entry in entries:
                if not entry:
                    continue
                
                title = entry.get('title', 'ملف ميديا')
                ext = entry.get('ext', 'mp4')
                expected_filename = f"{DOWNLOAD_DIR}/{entry['id']}.{ext}"
                
                if os.path.exists(expected_filename):
                    # جلب الأبعاد والصورة المصغرة للفيديو
                    width, height, duration, thumb = get_video_meta_and_thumb(expected_filename)
                    media_items.append({
                        "type": "فيديو 🎬",
                        "title": title,
                        "file_path": expected_filename,
                        "is_file": True,
                        "width": width,
                        "height": height,
                        "duration": duration,
                        "thumb": thumb
                    })
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
            logger.error(f"حدث خطأ أثناء الاستخراج أو التحميل: {e}")
            
    return media_items

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 مرحباً بك! أرسل لي الرابط، وسأقوم بتحميل ملف الميديا وإرساله لك كفيديو يدعم التشغيل الفوري والغلاف.")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_url = update.message.text
    user_chat_id = update.message.chat_id
    
    if "http" in user_url:
        status_message = await update.message.reply_text("⏳ جاري تحميل مقطع الفيديو وتوليد بيانات البث الفوري...")
        media_items = extract_and_download_media(user_url)
        
        if media_items:
            await status_message.delete()
            
            for index, item in enumerate(media_items, 1):
                try:
                    if item['is_file']:
                        # فتح الفيديو والصورة المصغرة وإرسالهما مع الأبعاد المطلوبة لتفعيل البث الفوري
                        with open(item['file_path'], 'rb') as video_file:
                            thumb_file = open(item['thumb'], 'rb') if item['thumb'] else None
                            
                            await context.bot.send_video(
                                chat_id=user_chat_id,
                                video=video_file,
                                width=item['width'],
                                height=item['height'],
                                duration=item['duration'],
                                thumbnail=thumb_file,
                                caption=f"🎯 **المادة رقم {index}**\n📝 العنوان: {item['title']}",
                                supports_streaming=True # تفعيل ميزة المشاهدة أثناء التحميل
                            )
                            
                            if thumb_file:
                                thumb_file.close()
                                os.remove(item['thumb']) # حذف الصورة المصغرة المؤقتة
                                
                        # تنظيف الفيديو من السيرفر بعد إرساله بناءً على رغبتك في توفير مساحة سيرفر Render
                        os.remove(item['file_path'])
                    else:
                        await context.bot.send_message(
                            chat_id=user_chat_id,
                            text=f"🎯 **المادة رقم {index}**\n📦 النوع: {item['type']}\n\n🔗 رابط الصورة:\n{item['url']}"
                        )
                except Exception as e:
                    logger.error(f"فشل إرسال الملف للمستخدم: {e}")
                    if item['is_file'] and os.path.exists(item['file_path']):
                        os.remove(item['file_path'])
                        
            await update.message.reply_text("🎉 تم إرسال الملفات بنجاح ودعم التشغيل الفوري.")
        else:
            await status_message.edit_text("❌ فشل تحميل الفيديو.")
    else:
        await update.message.reply_text("⚠️ من فضلك أرسل رابط ويب صحيح.")

def main():
    server_thread = Thread(target=run_web_server)
    server_thread.daemon = True
    server_thread.start()

    telegram_app = Application.builder().token(BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    
    telegram_app.run_polling()

if __name__ == '__main__':
    main()
                        
