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
    # إعدادات الفحص الأولي السريع بدون تحميل لتحديد نوع الميديا
    ydl_opts_info = {
        'extract_flat': False,
        'skip_download': True,
        'nocheckcertificate': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    }
    if os.path.exists('cookies.txt'):
        ydl_opts_info['cookiefile'] = 'cookies.txt'

    media_items = []
    
    with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
        try:
            info = ydl.extract_info(profile_url, download=False)
            entries = info.get('entries', [info])
            
            for entry in entries:
                if not entry:
                    continue
                
                # فحص هل الرابط يحتوي على فيديو فعلي
                is_video = entry.get('vcodec') != 'none' or 'video' in entry.get('extractor_key', '').lower()
                
                if is_video:
                    # إذا كان فيديو، نقوم بإنشاء إعدادات تحميل حقيقية وحفظه كملف mp4 لتشغيله الفوري
                    ydl_opts_dl = {
                        'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s',
                        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                        'nocheckcertificate': True,
                        'merge_output_format': 'mp4',
                    }
                    if os.path.exists('cookies.txt'):
                        ydl_opts_dl['cookiefile'] = 'cookies.txt'
                        
                    with yt_dlp.YoutubeDL(ydl_opts_dl) as ydl_dl:
                        info_dl = ydl_dl.extract_info(entry.get('webpage_url', profile_url), download=True)
                        ext = info_dl.get('ext', 'mp4')
                        expected_file = f"{DOWNLOAD_DIR}/{info_dl['id']}.{ext}"
                        
                        if os.path.exists(expected_file):
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
                    # 🖼️ إذا كان الرابط منشور صور، نستخرج الروابط المباشرة لجميع الصور بأعلى دقة متوفرة
                    if entry.get('thumbnails'):
                        best_url = entry['thumbnails'][-1]['url']
                        # تحسين الدقة لصور تويتر وجلب الحجم الأصلي
                        if 'twimg.com' in best_url:
                            if 'name=' in best_url:
                                best_url = best_url.split('&name=')[0] + '&name=large'
                            elif 'format=' in best_url:
                                best_url = best_url + '&name=large'
                        media_items.append({"type": "photo", "url": best_url})
                        
                    elif entry.get('url'):
                        best_url = entry['url']
                        if 'twimg.com' in best_url:
                            if 'name=' in best_url:
                                best_url = best_url.split('&name=')[0] + '&name=large'
                            elif 'format=' in best_url:
                                best_url = best_url + '&name=large'
                        media_items.append({"type": "photo", "url": best_url})
                        
        except Exception as e:
            logger.error(f"حدث خطأ أثناء الاستخراج: {e}")
            
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
    photo_group = []

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
            # إضافة رابط الصورة عالية الدقة مباشرة إلى مجموعة الألبوم
            photo_group.append(InputMediaPhoto(media=item["url"]))

    # إرسال ألبوم الصور المجمعة فوراً (كل رسالة تحتوي على 10 صور كحد أقصى تماشياً مع قواعد تلجرام)
    if photo_group:
        try:
            for i in range(0, len(photo_group), 10):
                await context.bot.send_media_group(chat_id=user_chat_id, media=photo_group[i:i+10])
        except Exception as e:
            logger.error(f"Error photo group transmit: {e}")

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
                    
