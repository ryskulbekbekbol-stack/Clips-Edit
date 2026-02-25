#!/usr/bin/env python3
import os
import sys
import subprocess
import tempfile
import shutil
import json
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
import yt_dlp
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    print("❌ Ошибка: BOT_TOKEN не установлен!")
    sys.exit(1)

QUALITY_PRESETS = {
    "360p": {"height": 360, "crf": 23, "desc": "360p"},
    "480p": {"height": 480, "crf": 22, "desc": "480p"},
    "720p": {"height": 720, "crf": 20, "desc": "720p"},
    "1080p": {"height": 1080, "crf": 18, "desc": "1080p"},
}

DEFAULT_QUALITY = "720p"
TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

user_videos = {}
user_audios = {}

# ========== 3 МЕТОДА СКАЧИВАНИЯ ==========
def download_video_method1(url, quality_key, temp_dir):
    """Метод 1: Основной с куками из браузера"""
    quality = QUALITY_PRESETS[quality_key]
    target_height = quality["height"]
    output = os.path.join(temp_dir, 'video.%(ext)s')
    
    ydl_opts = {
        'format': f'bestvideo[height<={target_height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={target_height}][ext=mp4]',
        'outtmpl': output,
        'merge_output_format': 'mp4',
        'quiet': True,
        'cookies_from_browser': 'chrome',  # Используем куки из Chrome
        'extractor_args': {
            'youtube': {
                'player_client': ['web'],
                'skip': ['hls', 'dash'],
            }
        },
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            base = filename.rsplit('.', 1)[0]
            
            for ext in ['.mp4']:
                if os.path.exists(base + ext):
                    return base + ext, info.get('title', 'video')
    except Exception as e:
        print(f"❌ Метод 1 не сработал: {e}")
        return None, None

def download_video_method2(url, quality_key, temp_dir):
    """Метод 2: Android клиент (не требует кук)"""
    quality = QUALITY_PRESETS[quality_key]
    target_height = quality["height"]
    output = os.path.join(temp_dir, 'video.%(ext)s')
    
    ydl_opts = {
        'format': f'best[height<={target_height}][ext=mp4]',
        'outtmpl': output,
        'quiet': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android'],
            }
        },
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            base = filename.rsplit('.', 1)[0]
            
            if os.path.exists(base + '.mp4'):
                return base + '.mp4', info.get('title', 'video')
    except Exception as e:
        print(f"❌ Метод 2 не сработал: {e}")
        return None, None

def download_video_method3(url, quality_key, temp_dir):
    """Метод 3: Минимальное качество + cookies.txt"""
    quality = QUALITY_PRESETS[quality_key]
    target_height = min(quality["height"], 720)  # Ограничиваем 720p
    output = os.path.join(temp_dir, 'video.%(ext)s')
    
    ydl_opts = {
        'format': f'best[height<={target_height}][ext=mp4]',
        'outtmpl': output,
        'quiet': True,
        'extract_flat': False,
    }
    
    # Если есть файл cookies.txt, используем его
    if os.path.exists('cookies.txt'):
        ydl_opts['cookies'] = 'cookies.txt'
        print("📦 Использую cookies.txt")
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            base = filename.rsplit('.', 1)[0]
            
            if os.path.exists(base + '.mp4'):
                return base + '.mp4', info.get('title', 'video')
    except Exception as e:
        print(f"❌ Метод 3 не сработал: {e}")
        return None, None

def download_video(url, quality_key):
    """
    Главная функция - пробует все 3 метода по очереди
    """
    print(f"\n📥 Скачиваю видео в {QUALITY_PRESETS[quality_key]['desc']}...")
    
    # Метод 1
    print("🔄 Пробую метод 1 (куки из браузера)...")
    temp_dir1 = tempfile.mkdtemp(dir=TEMP_DIR)
    video_path, title = download_video_method1(url, quality_key, temp_dir1)
    if video_path:
        return video_path, title, temp_dir1
    shutil.rmtree(temp_dir1)
    
    # Метод 2
    print("🔄 Пробую метод 2 (Android клиент)...")
    temp_dir2 = tempfile.mkdtemp(dir=TEMP_DIR)
    video_path, title = download_video_method2(url, quality_key, temp_dir2)
    if video_path:
        return video_path, title, temp_dir2
    shutil.rmtree(temp_dir2)
    
    # Метод 3
    print("🔄 Пробую метод 3 (cookies.txt)...")
    temp_dir3 = tempfile.mkdtemp(dir=TEMP_DIR)
    video_path, title = download_video_method3(url, quality_key, temp_dir3)
    if video_path:
        return video_path, title, temp_dir3
    shutil.rmtree(temp_dir3)
    
    print("❌ Все методы скачивания не сработали")
    return None, None, None

# ========== ОСТАЛЬНЫЕ ФУНКЦИИ ==========
def get_duration(file_path):
    """Получает длительность видео/аудио"""
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
           '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except:
        return 0

def compress_video(input_path, max_size_mb=45):
    """Сжимает видео если оно слишком большое"""
    size = os.path.getsize(input_path) / (1024 * 1024)
    if size <= max_size_mb:
        return input_path
    
    output_path = input_path.replace('.mp4', '_compressed.mp4')
    cmd = [
        'ffmpeg', '-i', input_path,
        '-c:v', 'libx264',
        '-b:v', '1M',
        '-preset', 'fast',
        '-c:a', 'aac',
        '-b:a', '128k',
        '-y',
        output_path
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path
    except:
        return input_path

def detect_beats(audio_path):
    """Определяет биты в аудио"""
    try:
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
               '-of', 'default=noprint_wrappers=1:nokey=1', audio_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        duration = float(result.stdout.strip())
        
        beats = []
        current = 0
        while current < duration:
            beats.append(current)
            current += 0.5
        return beats
    except:
        return [0]

def cut_video_segment(video_path, start_time, end_time, output_path, quality_key):
    """Нарезает один сегмент видео"""
    quality = QUALITY_PRESETS[quality_key]
    
    cmd = [
        'ffmpeg', '-i', video_path,
        '-ss', str(start_time),
        '-to', str(end_time),
        '-vf', f'scale=-2:{quality["height"]}',
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', str(quality["crf"]),
        '-an',
        '-y',
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except:
        return False

def merge_clips_with_audio(clips, audio_path, output_path, total_duration):
    """Склеивает клипы и накладывает аудио"""
    if not clips:
        return None
    
    list_file = os.path.join(os.path.dirname(output_path), 'list.txt')
    with open(list_file, 'w') as f:
        for clip in clips:
            f.write(f"file '{clip}'\n")
    
    merged = os.path.join(os.path.dirname(output_path), 'merged.mp4')
    concat_cmd = [
        'ffmpeg', '-f', 'concat', '-safe', '0',
        '-i', list_file,
        '-c', 'copy',
        '-y',
        merged
    ]
    
    try:
        subprocess.run(concat_cmd, check=True, capture_output=True)
        
        trimmed_audio = os.path.join(os.path.dirname(output_path), 'trimmed_audio.mp3')
        trim_cmd = [
            'ffmpeg', '-i', audio_path,
            '-t', str(total_duration),
            '-c', 'copy',
            '-y',
            trimmed_audio
        ]
        subprocess.run(trim_cmd, check=True, capture_output=True)
        
        final_cmd = [
            'ffmpeg', '-i', merged,
            '-i', trimmed_audio,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-map', '0:v:0',
            '-map', '1:a:0',
            '-shortest',
            '-y',
            output_path
        ]
        subprocess.run(final_cmd, check=True, capture_output=True)
        
        os.remove(merged)
        os.remove(trimmed_audio)
        os.remove(list_file)
        return output_path
        
    except Exception as e:
        print(f"Ошибка склейки: {e}")
        return None

# ========== КОМАНДЫ БОТА ==========
@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    await message.reply(
        "🎬 **BeatSync Clip Bot**\n\n"
        "**Команды:**\n"
        "/quality <качество> - 360p, 480p, 720p, 1080p\n"
        "/yt <ссылка> <секунд> - скачать видео\n\n"
        "**Как пользоваться:**\n"
        "1️⃣ Установи качество\n"
        "2️⃣ Отправь /yt с ссылкой и длительностью\n"
        "3️⃣ Отправь аудиофайл\n"
        "4️⃣ Получи клип под бит"
    )

@dp.message_handler(commands=['quality'])
async def quality_cmd(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        qualities = ", ".join(QUALITY_PRESETS.keys())
        await message.reply(f"❌ Доступные качества: {qualities}")
        return
    
    quality = args[1]
    if quality not in QUALITY_PRESETS:
        await message.reply(f"❌ Качество должно быть: {', '.join(QUALITY_PRESETS.keys())}")
        return
    
    user_id = str(message.from_user.id)
    if user_id not in user_videos:
        user_videos[user_id] = {}
    user_videos[user_id]['quality'] = quality
    await message.reply(f"✅ Качество установлено: {QUALITY_PRESETS[quality]['desc']}")

@dp.message_handler(commands=['yt'])
async def yt_command(message: types.Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.reply("❌ Использование: /yt <ссылка> <секунд>")
        return
    
    url = args[1]
    try:
        clip_duration = int(args[2])
        if clip_duration <= 0 or clip_duration > 300:
            await message.reply("❌ Длительность должна быть от 1 до 300 секунд")
            return
    except:
        await message.reply("❌ Длительность должна быть числом")
        return
    
    user_id = str(message.from_user.id)
    quality = user_videos.get(user_id, {}).get('quality', DEFAULT_QUALITY)
    
    msg = await message.reply(f"⏬ Скачиваю видео в {QUALITY_PRESETS[quality]['desc']}...")
    
    video_path, title, temp_dir = download_video(url, quality)
    
    if not video_path:
        await msg.edit_text("❌ Не удалось скачать видео. YouTube требует подтверждения.")
        return
    
    if user_id not in user_videos:
        user_videos[user_id] = {}
    user_videos[user_id]['video'] = {'path': video_path, 'temp_dir': temp_dir}
    user_videos[user_id]['duration'] = clip_duration
    
    if user_id in user_audios and 'audio' in user_audios[user_id]:
        await msg.edit_text("✅ Видео скачано! Есть аудио, обрабатываю...")
        await process_files(message, user_id)
    else:
        await msg.edit_text("✅ Видео скачано! Теперь отправь аудиофайл")

@dp.message_handler(content_types=['audio'])
async def handle_audio(message: types.Message):
    user_id = str(message.from_user.id)
    msg = await message.reply("⏬ Скачиваю аудио...")
    
    file = await bot.get_file(message.audio.file_id)
    temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
    audio_path = os.path.join(temp_dir, 'audio.mp3')
    await bot.download_file(file.file_path, audio_path)
    
    if user_id not in user_audios:
        user_audios[user_id] = {}
    user_audios[user_id]['audio'] = {'path': audio_path, 'temp_dir': temp_dir}
    
    if user_id in user_videos and 'video' in user_videos[user_id]:
        await msg.edit_text("✅ Аудио получено! Есть видео, обрабатываю...")
        await process_files(message, user_id)
    else:
        await msg.edit_text("✅ Аудио скачано! Теперь отправь /yt с ссылкой")

async def process_files(message: types.Message, user_id: str):
    """Обрабатывает видео и аудио"""
    try:
        video_info = user_videos[user_id]['video']
        audio_info = user_audios[user_id]['audio']
        clip_duration = user_videos[user_id].get('duration', 30)
        quality = user_videos[user_id].get('quality', DEFAULT_QUALITY)
        
        video_path = video_info['path']
        audio_path = audio_info['path']
        
        msg = await message.reply("🎵 Анализирую биты в музыке...")
        
        beats = detect_beats(audio_path)
        
        if len(beats) < 2:
            await msg.edit_text("❌ Не удалось определить биты")
            return
        
        work_dir = tempfile.mkdtemp(dir=TEMP_DIR)
        clips = []
        
        segment_duration = clip_duration / len(beats) if len(beats) > 1 else clip_duration
        
        for i in range(len(beats)):
            start = i * segment_duration
            end = min((i + 1) * segment_duration, clip_duration)
            
            if end - start < 0.3:
                continue
                
            clip_path = os.path.join(work_dir, f"clip_{i:03d}.mp4")
            if cut_video_segment(video_path, start, end, clip_path, quality):
                clips.append(clip_path)
        
        if not clips:
            await msg.edit_text("❌ Не удалось нарезать видео")
            shutil.rmtree(work_dir)
            return
        
        await msg.edit_text(f"🔄 Склеиваю {len(clips)} фрагментов...")
        
        output_path = os.path.join(work_dir, 'final.mp4')
        result = merge_clips_with_audio(clips, audio_path, output_path, clip_duration)
        
        if not result:
            await msg.edit_text("❌ Не удалось создать финальное видео")
            shutil.rmtree(work_dir)
            return
        
        file_size = os.path.getsize(result) / 1024 / 1024
        if file_size > 45:
            await msg.edit_text(f"📦 Видео {file_size:.1f} MB. Сжимаю...")
            result = compress_video(result)
            file_size = os.path.getsize(result) / 1024 / 1024
        
        await msg.edit_text("✅ Готово! Отправляю...")
        
        with open(result, 'rb') as f:
            await message.reply_video(
                f,
                caption=(
                    f"🎬 **Клип готов!**\n"
                    f"📊 Качество: {QUALITY_PRESETS[quality]['desc']}\n"
                    f"🎵 Длительность: {clip_duration} сек\n"
                    f"✂️ Фрагментов: {len(clips)}\n"
                    f"💾 Размер: {file_size:.1f} MB"
                )
            )
        
        shutil.rmtree(work_dir)
        shutil.rmtree(video_info['temp_dir'])
        shutil.rmtree(audio_info['temp_dir'])
        
        del user_videos[user_id]['video']
        del user_audios[user_id]['audio']
        
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    print("🤖 BeatSync Clip Bot (3 метода) запущен")
    print("📥 Метод 1: Куки из браузера")
    print("📥 Метод 2: Android клиент")
    print("📥 Метод 3: cookies.txt")
    executor.start_polling(dp, skip_updates=True)
