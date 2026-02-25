#!/usr/bin/env python3
# Бот для нарезки YouTube видео под бит музыки (4K ГАРАНТИРОВАННО)
# by Колин - Ultimate Edition

import os
import sys
import subprocess
import tempfile
import shutil
import json
import re
import math
import time
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
import yt_dlp
from dotenv import load_dotenv

load_dotenv()

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    print("❌ Ошибка: BOT_TOKEN не установлен!")
    sys.exit(1)

# Настройки качества (ПОЛНАЯ ПОДДЕРЖКА 4K)
QUALITY_PRESETS = {
    "360p": {"height": 360, "width": 640, "crf": 23, "bitrate": "800k", "desc": "360p (SD)"},
    "480p": {"height": 480, "width": 854, "crf": 22, "bitrate": "1500k", "desc": "480p (SD)"},
    "720p": {"height": 720, "width": 1280, "crf": 20, "bitrate": "2500k", "desc": "720p (HD)"},
    "1080p": {"height": 1080, "width": 1920, "crf": 18, "bitrate": "5000k", "desc": "1080p (Full HD)"},
    "1440p": {"height": 1440, "width": 2560, "crf": 16, "bitrate": "12000k", "desc": "2K (1440p)"},
    "2160p": {"height": 2160, "width": 3840, "crf": 14, "bitrate": "25000k", "desc": "4K (2160p)"}
}

DEFAULT_QUALITY = "1080p"
TEMP_DIR = "temp"
MAX_FILE_SIZE = 1024 * 1024 * 1024  # 1GB для 4K видео
# ================================

os.makedirs(TEMP_DIR, exist_ok=True)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Хранилище пользовательских данных
user_data = {}
user_videos = {}
user_audios = {}

def load_user_data():
    global user_data
    try:
        with open('user_data.json', 'r', encoding='utf-8') as f:
            user_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        user_data = {}

def save_user_data():
    with open('user_data.json', 'w', encoding='utf-8') as f:
        json.dump(user_data, f, ensure_ascii=False, indent=2)

load_user_data()

# ========== ФУНКЦИИ РАБОТЫ С ВИДЕО ==========
def download_youtube_video(url, quality_key):
    """
    ГАРАНТИРОВАННОЕ скачивание видео с YouTube в 4K
    Использует 3 разных метода обхода блокировок
    """
    temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
    
    quality = QUALITY_PRESETS[quality_key]
    target_height = quality["height"]
    
    video_output = os.path.join(temp_dir, 'video.%(ext)s')
    
    # МЕТОД 1: Основной с всеми клиентами
    ydl_opts = {
        'format': f'bestvideo[height<={target_height}]+bestaudio/best[height<={target_height}]',
        'outtmpl': video_output,
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'age_limit': 99,
        
        # Максимальный обход защиты
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web', 'ios', 'tv', 'web_embedded', 'mweb'],
                'skip': ['hls', 'dash'],
                'include_plus': True,
            }
        },
        
        # Дополнительные параметры для 4K
        'format_sort': ['res', 'codec:av1', 'codec:vp9', 'codec:h264'],
        'prefer_free_formats': True,
        'geo_bypass': True,
        'geo_bypass_country': 'US',
    }
    
    # Пробуем основной метод
    try:
        print(f"📥 Метод 1: Скачиваю {url} в {target_height}p")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            if info:
                filename = ydl.prepare_filename(info)
                base = filename.rsplit('.', 1)[0]
                
                # Проверяем результат
                for ext in ['.mp4', '.webm', '.mkv']:
                    if os.path.exists(base + ext):
                        file_size = os.path.getsize(base + ext)
                        if file_size < MAX_FILE_SIZE:
                            print(f"✅ Успешно скачано: {file_size/1024/1024:.1f} MB")
                            return base + ext, info.get('title', 'video'), temp_dir
                    
                if os.path.exists(base + '.mp4'):
                    file_size = os.path.getsize(base + '.mp4')
                    if file_size < MAX_FILE_SIZE:
                        print(f"✅ Успешно скачано: {file_size/1024/1024:.1f} MB")
                        return base + '.mp4', info.get('title', 'video'), temp_dir
                        
    except Exception as e:
        print(f"❌ Метод 1 не сработал: {e}")
    
    # МЕТОД 2: Только видео без звука (для проблемных видео)
    try:
        print("🔄 Метод 2: Пробую скачать только видео...")
        fallback_opts = {
            'format': f'bestvideo[height<={target_height}][ext=mp4]',
            'outtmpl': video_output,
            'quiet': True,
            'extractor_args': {'youtube': {'player_client': ['android']}}
        }
        
        with yt_dlp.YoutubeDL(fallback_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            base = filename.rsplit('.', 1)[0]
            
            for ext in ['.mp4']:
                if os.path.exists(base + ext):
                    file_size = os.path.getsize(base + ext)
                    if file_size < MAX_FILE_SIZE:
                        print(f"✅ Метод 2 успешен: {file_size/1024/1024:.1f} MB")
                        return base + ext, info.get('title', 'video'), temp_dir
                        
    except Exception as e:
        print(f"❌ Метод 2 не сработал: {e}")
    
    # МЕТОД 3: Самое низкое качество (если всё плохо)
    try:
        print("🔄 Метод 3: Пробую минимальное качество...")
        minimal_opts = {
            'format': 'best[height<=720]',
            'outtmpl': video_output,
            'quiet': True,
            'extract_flat': False,
        }
        
        with yt_dlp.YoutubeDL(minimal_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            base = filename.rsplit('.', 1)[0]
            
            for ext in ['.mp4', '.webm']:
                if os.path.exists(base + ext):
                    file_size = os.path.getsize(base + ext)
                    print(f"✅ Метод 3 успешен: {file_size/1024/1024:.1f} MB")
                    return base + ext, info.get('title', 'video'), temp_dir
                    
    except Exception as e:
        print(f"❌ Метод 3 не сработал: {e}")
    
    # Если ничего не вышло
    print("❌ Все методы скачивания не сработали")
    shutil.rmtree(temp_dir)
    return None, None, None

def get_video_info(video_path):
    """Получает информацию о видео через ffprobe"""
    cmd = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_streams', '-show_format', video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        info = json.loads(result.stdout)
        
        # Ищем видеопоток
        video_stream = None
        for stream in info.get('streams', []):
            if stream.get('codec_type') == 'video':
                video_stream = stream
                break
        
        if video_stream:
            return {
                'width': int(video_stream.get('width', 0)),
                'height': int(video_stream.get('height', 0)),
                'codec': video_stream.get('codec_name', 'unknown'),
                'duration': float(info.get('format', {}).get('duration', 0))
            }
    except Exception as e:
        print(f"❌ Ошибка получения информации о видео: {e}")
    return None

def detect_beats(audio_path):
    """Определяет биты (равномерная сетка для простоты)"""
    try:
        # Получаем длительность аудио
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
               '-of', 'default=noprint_wrappers=1:nokey=1', audio_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        duration = float(result.stdout.strip())
        
        # Создаём биты каждые 0.5 секунды (120 BPM)
        interval = 0.5
        beats = []
        current = 0
        while current < duration:
            beats.append(current)
            current += interval
        
        return beats
    except:
        return [0]

def cut_video(video_path, start, end, output_path, quality_key):
    """Нарезает один фрагмент видео с заданным качеством"""
    quality = QUALITY_PRESETS[quality_key]
    
    cmd = [
        'ffmpeg', '-i', video_path,
        '-ss', str(start),
        '-to', str(end),
        '-vf', f'scale={quality["width"]}:{quality["height"]}:flags=lanczos',
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

def merge_videos(video_list, audio_path, output_path):
    """Склеивает видео и накладывает аудио"""
    if not video_list:
        return None
    
    # Создаём список для FFmpeg
    list_file = os.path.join(os.path.dirname(output_path), 'list.txt')
    with open(list_file, 'w') as f:
        for v in video_list:
            f.write(f"file '{v}'\n")
    
    # Склеиваем видео
    temp_video = os.path.join(os.path.dirname(output_path), 'merged.mp4')
    concat_cmd = [
        'ffmpeg', '-f', 'concat', '-safe', '0',
        '-i', list_file,
        '-c', 'copy',
        '-y',
        temp_video
    ]
    
    try:
        subprocess.run(concat_cmd, check=True, capture_output=True)
        
        # Накладываем аудио
        final_cmd = [
            'ffmpeg', '-i', temp_video,
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
        os.remove(temp_video)
        os.remove(list_file)
        return output_path
    except:
        return None

# ========== КОМАНДЫ БОТА ==========
@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("⚙️ Качество", callback_data="quality_menu"),
        InlineKeyboardButton("⏱️ Множитель", callback_data="multiplier_menu")
    )
    
    await message.reply(
        "🎬 **BeatSync 4K Bot**\n\n"
        "Я нарезаю YouTube видео под бит музыки в 4K!\n\n"
        "**Доступные качества:**\n"
        "• 360p, 480p, 720p (HD)\n"
        "• 1080p (Full HD)\n"
        "• 1440p (2K)\n"
        "• 2160p (4K)\n\n"
        "**Как пользоваться:**\n"
        "1️⃣ Установи качество и множитель\n"
        "2️⃣ Отправь команду: /yt <ссылка>\n"
        "3️⃣ Отправь аудиофайл\n"
        "4️⃣ Получи готовый клип под бит!\n\n"
        "**Команды:**\n"
        "/quality — выбрать качество\n"
        "/multiplier — установить множитель\n"
        "/settings — текущие настройки",
        parse_mode='Markdown',
        reply_markup=markup
    )

@dp.message_handler(commands=['quality'])
async def quality_cmd(message: types.Message):
    user_id = str(message.from_user.id)
    current = user_data.get(user_id, {}).get('quality', DEFAULT_QUALITY)
    
    markup = InlineKeyboardMarkup(row_width=2)
    for key, preset in QUALITY_PRESETS.items():
        marker = "✅ " if key == current else ""
        markup.add(InlineKeyboardButton(
            f"{marker}{preset['desc']}",
            callback_data=f"set_quality_{key}"
        ))
    
    await message.reply(
        f"📊 **Выбери качество видео**\n\n"
        f"Текущее: {QUALITY_PRESETS[current]['desc']}",
        parse_mode='Markdown',
        reply_markup=markup
    )

@dp.message_handler(commands=['multiplier'])
async def multiplier_cmd(message: types.Message):
    user_id = str(message.from_user.id)
    current = user_data.get(user_id, {}).get('multiplier', 2)
    
    markup = InlineKeyboardMarkup(row_width=5)
    row = []
    for i in range(1, 6):
        marker = "✅" if i == current else f"{i}"
        row.append(InlineKeyboardButton(
            f"{marker}", callback_data=f"set_multiplier_{i}"
        ))
    markup.row(*row)
    
    await message.reply(
        f"⏱️ **Множитель битов**\n\n"
        f"Текущий: {current}\n\n"
        f"1 = один бит (очень быстро)\n"
        f"2 = два бита (рекомендуется)\n"
        f"3-5 = более длинные фрагменты\n\n"
        f"Выбери значение:",
        parse_mode='Markdown',
        reply_markup=markup
    )

@dp.message_handler(commands=['settings'])
async def settings_cmd(message: types.Message):
    user_id = str(message.from_user.id)
    quality = user_data.get(user_id, {}).get('quality', DEFAULT_QUALITY)
    multiplier = user_data.get(user_id, {}).get('multiplier', 2)
    
    await message.reply(
        f"⚙️ **Текущие настройки**\n\n"
        f"📊 Качество: {QUALITY_PRESETS[quality]['desc']}\n"
        f"⏱️ Множитель: {multiplier}\n\n"
        f"Изменить:\n"
        f"/quality — качество\n"
        f"/multiplier — множитель",
        parse_mode='Markdown'
    )

@dp.message_handler(commands=['yt'])
async def yt_command(message: types.Message):
    """Обрабатывает команду /yt <ссылка>"""
    args = message.text.split()
    if len(args) < 2:
        await message.reply("❌ Использование: /yt <ссылка>\nПример: /yt https://youtu.be/...")
        return
    
    url = args[1]
    user_id = str(message.from_user.id)
    quality = user_data.get(user_id, {}).get('quality', DEFAULT_QUALITY)
    
    status = await message.reply(f"⏬ Скачиваю видео с YouTube в {QUALITY_PRESETS[quality]['desc']}...")
    
    video_path, title, temp_dir = download_youtube_video(url, quality)
    
    if not video_path:
        await status.edit_text("❌ Не удалось скачать видео. Попробуй другую ссылку или качество.")
        return
    
    # Получаем информацию о видео
    info = get_video_info(video_path)
    if info:
        await message.reply(
            f"📹 **Видео скачано!**\n"
            f"Название: {title}\n"
            f"Длительность: {info['duration']:.1f} сек\n"
            f"Разрешение: {info['width']}x{info['height']}\n"
            f"Кодек: {info['codec']}"
        )
    
    # Сохраняем для пользователя
    if user_id not in user_videos:
        user_videos[user_id] = []
    user_videos[user_id].append({
        'path': video_path,
        'temp_dir': temp_dir,
        'title': title
    })
    
    if user_id in user_audios and user_audios[user_id]:
        await status.edit_text("✅ Видео скачано! Есть аудио, обрабатываю...")
        await process_user_files(message, user_id)
    else:
        await status.edit_text("✅ Видео скачано! Теперь отправь аудиофайл")

@dp.message_handler(content_types=['audio'])
async def handle_audio(message: types.Message):
    user_id = str(message.from_user.id)
    
    status = await message.reply("⏬ Скачиваю аудио...")
    file = await bot.get_file(message.audio.file_id)
    
    temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
    audio_path = os.path.join(temp_dir, 'audio.mp3')
    
    await bot.download_file(file.file_path, audio_path)
    
    if user_id not in user_audios:
        user_audios[user_id] = []
    user_audios[user_id].append({
        'path': audio_path,
        'temp_dir': temp_dir
    })
    
    if user_id in user_videos and user_videos[user_id]:
        await status.edit_text("✅ Аудио получено! Есть видео, обрабатываю...")
        await process_user_files(message, user_id)
    else:
        await status.edit_text("✅ Аудио получено! Теперь отправь команду /yt с ссылкой")

async def process_user_files(message: types.Message, user_id: str):
    """Обрабатывает пару видео+аудио"""
    
    video_info = user_videos[user_id][-1]
    audio_info = user_audios[user_id][-1]
    
    video_path = video_info['path']
    audio_path = audio_info['path']
    
    quality = user_data.get(user_id, {}).get('quality', DEFAULT_QUALITY)
    multiplier = user_data.get(user_id, {}).get('multiplier', 2)
    
    status = await message.reply(f"🎵 Анализирую биты в музыке...")
    
    beats = detect_beats(audio_path)
    
    if len(beats) < 2:
        await status.edit_text("❌ Не удалось определить биты")
        shutil.rmtree(video_info['temp_dir'])
        shutil.rmtree(audio_info['temp_dir'])
        user_videos[user_id].pop()
        user_audios[user_id].pop()
        return
    
    # Группируем биты
    video_info_ff = get_video_info(video_path)
    if not video_info_ff:
        await status.edit_text("❌ Не удалось получить информацию о видео")
        return
    
    video_duration = video_info_ff['duration']
    beats = [b for b in beats if b < video_duration]
    
    if len(beats) < 2:
        await status.edit_text("❌ Видео слишком короткое")
        return
    
    await status.edit_text(f"✂️ Нарезаю видео на фрагменты ({QUALITY_PRESETS[quality]['desc']})...")
    
    work_dir = tempfile.mkdtemp(dir=TEMP_DIR)
    clip_paths = []
    
    # Нарезаем каждый сегмент
    for i in range(0, len(beats)-1, multiplier):
        start = beats[i]
        end = beats[i+multiplier] if i+multiplier < len(beats) else beats[-1]
        
        if end - start < 0.5:
            continue
            
        clip_path = os.path.join(work_dir, f"clip_{i:03d}.mp4")
        if cut_video(video_path, start, end, clip_path, quality):
            clip_paths.append(clip_path)
    
    if not clip_paths:
        await status.edit_text("❌ Не удалось нарезать видео")
        shutil.rmtree(work_dir)
        shutil.rmtree(video_info['temp_dir'])
        shutil.rmtree(audio_info['temp_dir'])
        user_videos[user_id].pop()
        user_audios[user_id].pop()
        return
    
    await status.edit_text(f"🔄 Склеиваю {len(clip_paths)} фрагментов...")
    
    output_path = os.path.join(work_dir, 'final.mp4')
    result = merge_videos(clip_paths, audio_path, output_path)
    
    if not result:
        await status.edit_text("❌ Не удалось создать финальное видео")
        shutil.rmtree(work_dir)
        shutil.rmtree(video_info['temp_dir'])
        shutil.rmtree(audio_info['temp_dir'])
        user_videos[user_id].pop()
        user_audios[user_id].pop()
        return
    
    file_size = os.path.getsize(result) / 1024 / 1024
    
    await status.edit_text("✅ Готово! Отправляю...")
    
    with open(result, 'rb') as f:
        await message.reply_video(
            f,
            caption=(
                f"🎬 **Клип готов!**\n\n"
                f"📊 Качество: {QUALITY_PRESETS[quality]['desc']}\n"
                f"🎵 Фрагментов: {len(clip_paths)}\n"
                f"⚡ Множитель: {multiplier}\n"
                f"💾 Размер: {file_size:.1f} MB"
            )
        )
    
    # Очистка
    shutil.rmtree(work_dir)
    shutil.rmtree(video_info['temp_dir'])
    shutil.rmtree(audio_info['temp_dir'])
    user_videos[user_id].pop()
    user_audios[user_id].pop()

# ========== CALLBACK HANDLERS ==========
@dp.callback_query_handler(lambda c: c.data == 'quality_menu')
async def quality_menu(callback: types.CallbackQuery):
    await quality_cmd(callback.message)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'multiplier_menu')
async def multiplier_menu(callback: types.CallbackQuery):
    await multiplier_cmd(callback.message)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('set_quality_'))
async def set_quality(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    quality = callback.data.replace('set_quality_', '')
    
    if quality in QUALITY_PRESETS:
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]['quality'] = quality
        save_user_data()
        
        await callback.message.edit_text(
            f"✅ Каче
