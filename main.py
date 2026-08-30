import os
import logging
import cv2  # مكتبة OpenCV لجلب أبعاد الفيديو وتوليد الصورة المصغرة تلقائياً
from threading import Thread
from flask import Flask
import yt_dlp
from telegram import Update, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# تسجيل الأخطاء
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask('')

@app.route('/')
def home():
    return "بوت التحميل الفوري الشامل النظيف يعمل!"

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
            # نقوم أولاً بفحص البيانات دون تحميل لمعرفة البنية
            info = ydl.extract_info(profile_url, download=False)
            
            # التحقق مما إذا كان المنشور يحتوي على ألبوم صور أو مدخلات متعددة
            entries = info.get('entries', [])
            
            if not entries:
                # نتحقق هل هو فيديو أم صورة
                is_video = info.get('vcodec') != 'none' or 'video' in info.get('extractor_key', '').lower()
                
                if is_video:
                    # تحميله فعلياً كفيديو
                    info_download = ydl.extract_info(profile_url, download=True)
                    ext = info_download.get('ext', 'mp4')
                    expected_filename = f"{DOWNLOAD_DIR}/{info_download['id']}.{ext}"
                    if os.path.exists(expected_filename):
                        width, height, duration, thumb = get_video_meta_and_thumb(expected_filename)
                        media_items.append({
                            "type": "فيديو 🎬",
                            "file_path": expected_filename,
                            "is_file": True,
                            "width": width,
                            "height": height,
                            "duration": duration,
                            "thumb": thumb
                        })
                else:
                    # معالجة كصورة منفردة
                    if info.get('thumbnails'):
                        best_image_url = info['thumbnails'][-1]['url']
                        if 'twimg.com' in best_image_url and 'name=' in best_image_url:
                            best_image_url = best_image_url.split('&name=') + '&name=large'
                        media_items.append({
                            "type": "صورة 🖼️",
                            "url": best_image_url,
                            "is_file": False
                        })
            else:
                # إذا كانت هناك مدخلات متعددة (ألبوم صور أو عدة فيديوهات معاً)
                for entry in entries:
                    if not entry:
                        continue
                    
                    is_video = entry.get('vcodec') != 'none' or 'video' in entry.get('extractor_key', '').lower()
                    
                    if is_video:
                        # تحميل الفيديو المحدد من الألبوم
                        entry_url = entry.get('webpage_url') or profile_url
                        info_download = ydl.extract_info(entry_url, download=True)
                        ext = info_download.get('ext', 'mp4')
                        expected_filename = f"{DOWNLOAD_DIR}/{info_download['id']}.{ext}"
                        if os.path.exists(expected_filename):
                            width, height, duration, thumb = get_video_meta_and_thumb(expected_filename)
                            media_items.append({
                                "type": "فيديو 🎬",
                                "file_path": expected_filename,
                                "is_file": True,
                                "width": width,
                                "height": height,
                                "duration": duration,
                                "thumb": thumb
                            })
                    else:
                        # معالجة الصور داخل الألبوم الجماعي
                        if entry.get('thumbnails'):
                            best_image_url = entry['thumbnails'][-1]['url']
                            if 'twimg.com' in best_image_url and 'name=' in best_image_url:
                                best_image_url = best_image_url.split('&name=') + '&name=large'
                            media_items.append({
                                "type": "صورة 🖼️",
                                "url": best_image_url,
                                "is_file": False
                            })
                        elif entry.get('url') and not is_video:
                            best_image_url = entry['url']
                            if 'twimg.com' in best_image_url and 'name=' in best_image_url:
                                best_image_url = best_image_url.split('&name=') + '&name=large'
                            media_items.append({
                                "type": "صورة 🖼️",
                                "url": best_image_url,
                                "is_file": False
                            })
                            
        except Exception as e:
            logger.error(f"حدث خطأ أثناء الاستخراج أو التحميل: {e}")
            
    return media_items

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 مرحباً بك! أرسل لي الرابط، وسأقوم بإرسال الفيديو أو مجموعة الصور لك نظيفة تماماً بدون أي كتابات وبدعم الألبومات والتشغيل الفوري.")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_url = update.message.text
    user_chat_id = update.message.chat_id
    
    if "http" in user_url:
        status_message = await update.message.reply_text("⏳ جاري سحب وتحليل الميديا بالكامل...")
        media_items = extract_and_download_media(user_url)
        
        if media_items:
            await status_message.delete()
            
            photo_group = []
            
            for item in media_items:
                try:
                    if item['is_file']:
                        with open(item['file_path'], 'rb') as video_file:
                            thumb_file = open(item['thumb'], 'rb') if item['thumb'] else None
                            
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
                                os.remove(item['thumb'])
                                
                        os.remove(item['file_path'])
                    else:
                        photo_group.append(InputMediaPhoto(media=item['url']))
                except Exception as e:
                    logger.error(f"فشل إرسال الملف: {e}")
                    if item['is_file'] and os.path.exists(item['file_path']):
                        os.remove(item['file_path'])
            
            # إرسال الصور المجمعة كألبوم مع ضبط المسافات البرمجية بدقة لمنع الخطأ
            if photo_group:
                try:
                    for i in range(0, len(photo_group), 10):
                        await context.bot.send_media_group(chat_id=user_chat_id, media=photo_group[i:i+10])
                except Exception as e:
                    logger.error(f"فشل إرسال ألبوم الصور: {e}")
        else:
            await status_message.edit_text("❌ فشل جلب الميديا.")
    else:
        await update.message.reply_text("⚠️ من فضلك أرسل رابط ويب صحيح.")

def main():
    server_thread = Thread(target=run_web_server)
    server_thread.daemon = True
    server_thread.start()

