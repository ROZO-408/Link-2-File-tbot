import os
import logging
import cv2
from threading import Thread
from flask import Flask
import yt_dlp
from telegram import Update, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask('')

@app.route('/')
def home():
    return "البوت الشامل النظيف يعمل!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

def get_video_meta_and_thumb(video_path):
    width, height, duration, thumb_path = 0, 0, 0, video_path + "_thumb.jpg"
    try:
        cap = cv2.VideoCapture(video_path)
        if cap.isOpened():
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if fps > 0:
                duration = int(frame_count / fps)
            ret, frame = cap.read()
            if ret:
                cv2.imwrite(thumb_path, frame)
        cap.release()
    except Exception as e:
        logger.error(f"Error meta: {e}")
    return width, height, duration, thumb_path if os.path.exists(thumb_path) else None

def extract_and_download_media(profile_url):
    ydl_opts = {
        'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s',
        # سماح بتحميل أفضل جودة للفيديو أو الصور المتاحة
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/bestimages/best',
        'playlist_items': '1-10',
        'nocheckcertificate': True,
        'merge_output_format': 'mp4',
        'writethumbnail': True, # إجبار المحرك على تحميل الصور كملفات محلية لتفادي الحظر
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    }
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'

    media_items = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            # تحميل الميديا مباشرة لتجاوز الحظر وحماية السيرفرات
            info = ydl.extract_info(profile_url, download=True)
            entries = info.get('entries', [info])
            
            for entry in entries:
                if not entry:
                    continue
                
                # فحص هل المادة فيديو أم صورة بناءً على الحزم المحملة
                is_video = entry.get('vcodec') != 'none' or 'video' in entry.get('extractor_key', '').lower()
                ext = entry.get('ext', 'mp4')
                expected_file = f"{DOWNLOAD_DIR}/{entry['id']}.{ext}"
                
                if is_video and os.path.exists(expected_file):
                    width, height, duration, thumb = get_video_meta_and_thumb(expected_file)
                    media_items.append({
                        "type": "video",
                        "file_path": expected_file,
                        "width": width,
                        "height": height,
                        "duration": duration,
                        "thumb": thumb
                    })
                else:
                    # معالجة الصور التي تم تحميلها كملفات محلية (jpg, png, webp, jpeg)
                    found_photo = False
                    for possible_ext in ['jpg', 'jpeg', 'png', 'webp']:
                        photo_file = f"{DOWNLOAD_DIR}/{entry['id']}.{possible_ext}"
                        if os.path.exists(photo_file):
                            media_items.append({"type": "photo", "file_path": photo_file})
                            found_photo = True
                            break
                    
                    # حل احتياطي إذا تم تحميل الصورة المصغرة فقط كمستند منفصل
                    if not found_photo:
                        thumb_file = f"{DOWNLOAD_DIR}/{entry['id']}.jpg"
                        if os.path.exists(thumb_file):
                            media_items.append({"type": "photo", "file_path": thumb_file})
                            
        except Exception as e:
            logger.error(f"Error extracting/downloading: {e}")
    return media_items

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 أرسل الرابط وسأجلب لك الصور أو الفيديوهات بشكل نظيف وتلقائي.")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_url = update.message.text
    user_chat_id = update.message.chat_id
    
    if "http" not in user_url:
        await update.message.reply_text("⚠️ من فضلك أرسل رابط ويب صحيح.")
        return

    status_message = await update.message.reply_text("⏳ جاري سحب الميديا النظيفة بالكامل...")
    media_items = extract_and_download_media(user_url)
    
    if not media_items:
        await status_message.edit_text("❌ فشل جلب الميديا من الرابط.")
        return

    await status_message.delete()
    photo_files_to_send = []

    for item in media_items:
        if item["type"] == "video":
            try:
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
            except Exception as e:
                logger.error(f"Error video transmit: {e}")
                if os.path.exists(item['file_path']):
                    os.remove(item['file_path'])
        
        elif item["type"] == "photo":
            photo_files_to_send.append(item["file_path"])

    # معالجة وإرسال الصور المجمعة محلياً كألبوم نظيف
    if photo_files_to_send:
        try:
            # نقوم بتقسيم الصور لمجموعات ألبومات (كل ألبوم 10 صور بحد أقصى)
            for i in range(0, len(photo_files_to_send), 10):
                chunk = photo_files_to_send[i:i+10]
                media_group = []
                opened_files = []
                
                for file_path in chunk:
                    f = open(file_path, 'rb')
                    opened_files.append(f)
                    media_group.append(InputMediaPhoto(media=f))
                
                if media_group:
                    await context.bot.send_media_group(chat_id=user_chat_id, media=media_group)
                
                # إغلاق الملفات وحذفها فوراً من السيرفر لتوفير المساحة بعد الإرسال
                for f in opened_files:
                    f.close()
                for file_path in chunk:
                    if os.path.exists(file_path):
                        os.remove(file_path)
        except Exception as e:
            logger.error(f"Error photo group transmit: {e}")
            # تنظيف احتياطي للملفات في حال فشل الإرسال
            for file_path in photo_files_to_send:
                if os.path.exists(file_path):
                    os.remove(file_path)

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
                    
