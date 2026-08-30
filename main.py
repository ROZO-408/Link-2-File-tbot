import os
import logging
import cv2
import subprocess
from threading import Thread
from flask import Flask
import yt_dlp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask('')

@app.route('/')
def home():
    return "بوت تحميل الفيديوهات الفوري الصافي والمطور يعمل!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

def get_video_meta_and_thumb(video_path):
    """
    دالة مطورة تعتمد على محركين (OpenCV و FFmpeg) لضمان جلب أبعاد الفيديو
    وتوليد صورة مصغرة صحيحة تمنع ظهور الفيديو كمستند أسود نهائياً.
    """
    width, height, duration = 640, 360, 0  # أبعاد افتراضية آمنة في حال الفشل
    thumb_path = video_path + "_thumb.jpg"
    
    # المحرك الأول: استخدام OpenCV والتقاط إطار متقدم لتفادي التلف البرمجي في البداية
    try:
        cap = cv2.VideoCapture(video_path)
        if cap.isOpened():
            width_val = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height_val = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if width_val > 0 and height_val > 0:
                width, height = width_val, height_val
                
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if fps > 0:
                duration = int(frame_count / fps)
            
            # الانتقال للإطار رقم 5 لتجنب الإطارات الأولى التالفة أو السوداء
            cap.set(cv2.CAP_PROP_POS_FRAMES, min(5, max(0, frame_count - 1)))
            ret, frame = cap.read()
            if ret:
                cv2.imwrite(thumb_path, frame)
        cap.release()
    except Exception as e:
        logger.error(f"OpenCV meta error: {e}")

    # المحرك الثاني والاحتياطي: استخدام FFmpeg قسرياً إذا فشل OpenCV في توليد الصورة
    if not os.path.exists(thumb_path) or os.path.getsize(thumb_path) == 0:
        try:
            # التقاط صورة عند الثانية 00:00:01 عبر أدوات النظام
            cmd = [
                'ffmpeg', '-y', '-ss', '00:00:01', '-i', video_path,
                '-vframes', '1', '-q:v', '2', thumb_path
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except Exception as e:
            logger.error(f"FFmpeg fallback thumbnail error: {e}")
            
    return width, height, duration, thumb_path if os.path.exists(thumb_path) else None

def extract_and_download_video(profile_url):
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

    video_items = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(profile_url, download=True)
            entries = info.get('entries', [info])
            
            for entry in entries:
                if not entry:
                    continue
                
                is_video = entry.get('vcodec') != 'none' or 'video' in entry.get('extractor_key', '').lower()
                ext = entry.get('ext', 'mp4')
                expected_file = f"{DOWNLOAD_DIR}/{entry['id']}.{ext}"
                
                if is_video and os.path.exists(expected_file):
                    width, height, duration, thumb = get_video_meta_and_thumb(expected_file)
                    video_items.append({
                        'file_path': expected_file,
                        'width': width,
                        'height': height,
                        'duration': duration,
                        'thumb': thumb
                    })
        except Exception as e:
            logger.error(f"حدث خطأ أثناء تحميل الفيديو: {e}")
            
    return video_items

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 مرحباً بك! أرسل لي أي رابط يحتوي على فيديو، وسأقوم بمعالجته بدقة وإرساله فوراً كفيديو حقيقي يدعم البث.")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_url = update.message.text
    user_chat_id = update.message.chat_id
    
    if "http" not in user_url:
        await update.message.reply_text("⚠️ من فضلك أرسل رابط ويب صحيح.")
        return

    status_message = await update.message.reply_text("⏳ جاري تحميل الفيديو وتأمين بيانات البث الفوري...")
    video_items = extract_and_download_video(user_url)
    
    if not video_items:
        await status_message.edit_text("❌ لم يتم العثور على فيديوهات قابلة للتحميل في هذا الرابط.")
        return

    await status_message.delete()

    for item in video_items:
        try:
            with open(item['file_path'], 'rb') as video_file:
                thumb_file = open(item['thumb'], 'rb') if (item['thumb'] and os.path.exists(item['thumb'])) else None
                
                # إرسال الفيديو الصافي مع الأبعاد الإجبارية والمحرك الاحتياطي لتفعيل زر التشغيل الفوري دائماً
                await context.bot.send_video(
                    chat_id=user_chat_id,
                    video=video_file,
                    width=item['width'],
                    height=item['height'],
                    duration=item['duration'],
                    thumbnail=thumb_file,
                    supports_streaming=True
                )
                if thumb_file:
                    thumb_file.close()
                    if os.path.exists(item['thumb']):
                        os.remove(item['thumb'])
                    
            os.remove(item['file_path'])
        except Exception as e:
            logger.error(f"فشل إرسال الفيديو: {e}")
            if os.path.exists(item['file_path']):
                os.remove(item['file_path'])

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
    
