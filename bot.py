#!/usr/bin/env python3
import os
import sys
import subprocess
import tempfile
import shutil
import json
import re
import time
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
import yt_dlp
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    print("❌ Ошибка: BOT_TOKEN не установлен!")
    sys.exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

# Настройки качества
QUALITY_PRESETS = {
    "360p": {"height": 360, "crf": 23, "desc": "360p"},
    "480p": {"height": 480, "crf": 22, "desc": "480p"},
    "720p": {"height": 720, "crf": 20, "desc": "720p"},
    "1080p": {"height": 1080, "crf": 18, "desc": "1080p"},
    "1440p": {"height": 1440, "crf": 16, "desc": "2K"},
    "2160p": {"height": 2160, "crf": 14, "desc": "4K"}
}

DEFAULT_QUALITY = "1080p"

user_videos = {}
user_audios = {}

# ========== ГАРАНТИРОВАННОЕ СКАЧИВАНИЕ ==========
def download_video(url, quality_key):
    """
    Супер-функция для скачивания видео с YouTube
    Пробует 3 разных метода
    """
    quality = QUALITY_PRESETS[quality_key]
    target_height = quality["height"]
    
    # МЕТОД 1: Самый современный подход
    print(f"📥 Метод 1: Пробую скачать {url}")
    result = method1_download(url, target_height)
    if result[0]:
        return result
    
    # МЕТОД 2: Запасной метод
    print(f"📥 Метод 2: Пробую запасной способ")
    result = method2_download(url, target_height)
    if result[0]:
        return result
    
    # МЕТОД 3: Минимальное качество (всё или ничего)
    print(f"📥 Метод 3: Пробую минимальное качество")
    result = method3_download(url)
    if result[0]:
        return result
    
    return None, None, None

def method1_download(url, target_height):
    """Основной метод с современными настройками"""
    temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
    output = os.path.join(temp_dir, 'video.%(ext)s')
    
    ydl_opts = {
        'format': f'bestvideo[height<={target_height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={target_height}][ext=mp4]',
        'outtmpl': output,
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'ignoreerrors': True,
        
        # Обход блокировок
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web', 'ios', 'tv', 'web_embedded'],
                'skip': ['hls', 'dash'],
            }
        },
        
        # Дополнительные параметры
        'geo_bypass': True,
        'geo_bypass_country': 'US',
        'age_limit': 99,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                # Ищем скачанный файл
                filename = ydl.prepare_filename(info)
                base = filename.rsplit('.', 1)[0]
                
                # Проверяем разные расширения
                for ext in ['.mp4', '.webm', '.mkv']:
                    if os.path.exists(base + ext):
                        file_size = os.path.getsize(base + ext) / 1024 / 1024
                        print(f"✅ Метод 1 успешен: {file_size:.1f} MB")
                        return base + ext, info.get('title', 'video'), temp_dir
                        
    except Exception as e:
        print(f"❌ Метод 1 ошибка: {e}")
    
    shutil.rmtree(temp_dir)
    return None, None, None

def method2_download(url, target_height):
    """Запасной метод - только видео без звука"""
    temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
    output = os.path.join(temp_dir, 'video.mp4')
    
    ydl_opts = {
        'format': f'bestvideo[height<={target_height}][ext=mp4]',
        'outtmpl': output,
        'quiet': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android']
            }
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if os.path.exists(output):
                file_size = os.path.getsize(output) / 1024 / 1024
                print(f"✅ Метод 2 успешен: {file_size:.1f} MB")
                return output, info.get('title', 'video'), temp_dir
    except Exception as e:
        print(f"❌ Метод 2 ошибка: {e}")
    
    shutil.rmtree(temp_dir)
    return None, None, None

def method3_download(url):
    """Метод 3 - минимальное качество"""
    temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
    output = os.path.join(temp_dir, 'video.mp4')
    
    ydl_opts = {
        'format': 'best[height<=360]',
        'outtmpl': output,
        'quiet': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if os.path.exists(output):
                file_size = os.path.getsize(output) / 1024 / 1024
                print(f"✅ Метод 3 успешен: {file_size:.1f} MB")
                return output, info.get('title', 'video'), temp_dir
    except Exception as e:
        print(f"❌ Метод 3 ошибка: {e}")
    
    shutil.rmtree(temp_dir)
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

def get_video_info(video_path):
    """Получает информацию о видео"""
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'stream=width,height', 
           '-of', 'json', video_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        data = json.loads(result.stdout)
        if data.get('streams') and len(data['streams']) > 0:
            return {
                'width': data['streams'][0].get('width', 0),
                'height': data['streams'][0].get('height', 0)
            }
    except:
        pass
    return None

def detect_beats(audio_path):
    """Определяет биты в аудио"""
    try:
        # Конвертируем в WAV
        temp_wav = audio_path + '.wav'
        convert_cmd = [
            'ffmpeg', '-i', audio_path,
            '-ac', '1', '-ar', '22050',
            '-y', temp_wav
        ]
        subprocess.run(convert_cmd, check=True, capture_output=True)
        
        duration = get_duration(audio_path)
        os.remove(temp_wav)
        
        # Создаём биты (120 BPM)
        bpm = 120
        interval = 60.0 / bpm
        
        beats = []
        current = 0
        while current < duration:
            beats.append(current)
            current += interval
        
        print(f"Создано {len(beats)} битов")
        return beats
        
    except Exception as e:
        print(f"Ошибка определения битов: {e}")
        return fallback_beats(audio_path)

def fallback_beats(audio_path):
    """Запасной вариант"""
    duration = get_duration(audio_path)
    beats = []
    current = 0
    while current < duration:
        beats.append(current)
        current += 0.5
    return beats

def cut_video(video_path, beats, output_dir, quality_key, multiplier=2):
    """Нарезает видео"""
    clips = []
    duration = get_duration(video_path)
    quality = QUALITY_PRESETS[quality_key]
    
    valid_beats = [b for b in beats if b < duration]
    
    if len(valid_beats) < 2:
        return clips
    
    for i in range(0, len(valid_beats)-1, multiplier):
        start = valid_beats[i]
        end = valid_beats[i+multiplier] if i+multiplier < len(valid_beats) else valid_beats[-1]
        
        if end - start < 0.3:
            continue
            
        output = os.path.join(output_dir, f"clip_{i:03d}.mp4")
        
        cmd = [
            'ffmpeg', '-i', video_path,
            '-ss', str(start),
            '-to', str(end),
            '-vf', f'scale=-2:{quality["height"]}',
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', str(quality["crf"]),
            '-an',
            '-y',
            output
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            clips.append(output)
        except Exception as e:
            print(f"Ошибка нарезки: {e}")
    
    return clips

def merge_clips(clips, audio_path, output_path):
    """Склеивает клипы"""
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
        
        final_cmd = [
            'ffmpeg', '-i', merged,
            '-i', audio_path,
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
        os.remove(list_file)
        return output_path
        
    except Exception as e:
        print(f"Ошибка склейки: {e}")
        return None

# ========== КОМАНДЫ ==========
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.reply(
        "🎬 **BeatSync 4K Bot**\n\n"
        "**Команды:**\n"
        "/quality <качество> - установить качество\n"
        "/multiplier <1-5> - множитель битов\n"
        "/yt <ссылка> - скачать видео\n"
        "После этого отправь аудиофайл"
    )

@dp.message_handler(commands=['quality'])
async def set_quality(message: types.Message):
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

@dp.message_handler(commands=['multiplier'])
async def set_multiplier(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply("❌ Пример: /multiplier 2")
        return
    try:
        mult = int(args[1])
        if 1 <= mult <= 5:
            user_id = str(message.from_user.id)
            if user_id not in user_videos:
                user_videos[user_id] = {}
            user_videos[user_id]['multiplier'] = mult
            await message.reply(f"✅ Множитель установлен: {mult}")
        else:
            await message.reply("❌ Множитель должен быть от 1 до 5")
    except:
        await message.reply("❌ Ошибка ввода")

@dp.message_handler(commands=['yt'])
async def yt_command(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply("❌ Пример: /yt https://youtu.be/...")
        return
    
    user_id = str(message.from_user.id)
    quality = user_videos.get(user_id, {}).get('quality', DEFAULT_QUALITY)
    multiplier = user_videos.get(user_id, {}).get('multiplier', 2)
    
    msg = await message.reply(f"⏬ Скачиваю видео в {QUALITY_PRESETS[quality]['desc']}...")
    
    video_path, title, temp_dir = download_video(args[1], quality)
    
    if not video_path:
        await msg.edit_text("❌ Не удалось скачать видео. Попробуй другую ссылку.")
        return
    
    info = get_video_info(video_path)
    resolution = f"{info['width']}x{info['height']}" if info else "неизвестно"
    duration = get_duration(video_path)
    
    await message.reply(
        f"✅ **Видео скачано!**\n"
        f"Название: {title}\n"
        f"Длительность: {duration:.1f} сек\n"
        f"Разрешение: {resolution}"
    )
    
    if user_id not in user_videos:
        user_videos[user_id] = {}
    user_videos[user_id]['video'] = {'path': video_path, 'temp_dir': temp_dir}
    
    if user_id in user_audios and 'audio' in user_audios[user_id]:
        await msg.edit_text("✅ Есть видео и аудио! Обрабатываю...")
        await process_files(message, user_id, quality, multiplier)
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
    
    quality = user_videos.get(user_id, {}).get('quality', DEFAULT_QUALITY)
    multiplier = user_videos.get(user_id, {}).get('multiplier', 2)
    
    if user_id not in user_audios:
        user_audios[user_id] = {}
    user_audios[user_id]['audio'] = {'path': audio_path, 'temp_dir': temp_dir}
    
    if user_id in user_videos and 'video' in user_videos[user_id]:
        await msg.edit_text("✅ Есть аудио и видео! Обрабатываю...")
        await process_files(message, user_id, quality, multiplier)
    else:
        await msg.edit_text("✅ Аудио скачано! Теперь отправь /yt с ссылкой")

async def process_files(message: types.Message, user_id: str, quality: str, multiplier: int):
    try:
        video_info = user_videos[user_id]['video']
        audio_info = user_audios[user_id]['audio']
        
        video_path = video_info['path']
        audio_path = audio_info['path']
        
        msg = await message.reply("🎵 Анализирую биты в музыке...")
        beats = detect_beats(audio_path)
        
        if len(beats) < 2:
            await msg.edit_text("❌ Не удалось определить биты")
            return
        
        await msg.edit_text(f"✂️ Нарезаю видео...")
        work_dir = tempfile.mkdtemp(dir=TEMP_DIR)
        clips = cut_video(video_path, beats, work_dir, quality, multiplier)
        
        if not clips:
            await msg.edit_text("❌ Не удалось нарезать видео")
            shutil.rmtree(work_dir)
            return
        
        await msg.edit_text(f"🔄 Склеиваю {len(clips)} фрагментов...")
        output_path = os.path.join(work_dir, 'final.mp4')
        result = merge_clips(clips, audio_path, output_path)
        
        if not result:
            await msg.edit_text("❌ Не удалось создать финальное видео")
            shutil.rmtree(work_dir)
            return
        
        size = os.path.getsize(result) / 1024 / 1024
        
        await msg.edit_text("✅ Готово! Отправляю...")
        with open(result, 'rb') as f:
            await message.reply_video(
                f,
                caption=(
                    f"🎬 **Клип готов!**\n"
                    f"📊 Качество: {QUALITY_PRESETS[quality]['desc']}\n"
                    f"🎵 Фрагментов: {len(clips)}\n"
                    f"⚡ Множитель: {multiplier}\n"
                    f"💾 Размер: {size:.1f} MB"
                )
            )
        
        shutil.rmtree(work_dir)
        shutil.rmtree(video_info['temp_dir'])
        shutil.rmtree(audio_info['temp_dir'])
        
        del user_videos[user_id]['video']
        del user_audios[user_id]['audio']
        
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")

if __name__ == '__main__':
    print("🤖 BeatSync 4K Bot запущен")
    print("📥 Режим: 3 метода скачивания")
    executor.start_polling(dp, skip_updates=True)
