#!/usr/bin/env python3
# Бот для нарезки видео под бит музыки (4K Ready)
# by Колин

import os
import sys
import subprocess
import tempfile
import shutil
import json
import math
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
import yt_dlp
import librosa
import numpy as np
from dotenv import load_dotenv

load_dotenv()

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    print("❌ Ошибка: BOT_TOKEN не установлен!")
    sys.exit(1)

# Настройки качества
QUALITY_PRESETS = {
    "360p": {"height": 360, "width": 640, "crf": 23, "bitrate": "800k", "desc": "360p (SD)"},
    "480p": {"height": 480, "width": 854, "crf": 22, "bitrate": "1500k", "desc": "480p (SD)"},
    "720p": {"height": 720, "width": 1280, "crf": 20, "bitrate": "2500k", "desc": "720p (HD)"},
    "1080p": {"height": 1080, "width": 1920, "crf": 18, "bitrate": "5000k", "desc": "1080p (Full HD)"},
    "2K": {"height": 1440, "width": 2560, "crf": 16, "bitrate": "12000k", "desc": "2K (1440p)"},
    "4K": {"height": 2160, "width": 3840, "crf": 14, "bitrate": "25000k", "desc": "4K (2160p)"}
}

DEFAULT_QUALITY = "1080p"
MAX_FILE_SIZE = 200 * 1024 * 1024  # 200 MB для 4K контента
MAX_DURATION = 300  # 5 минут
BEAT_MULTIPLIER = 2
TEMP_DIR = "temp"
# ================================

os.makedirs(TEMP_DIR, exist_ok=True)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Хранилище пользовательских данных
user_data = {}

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

# ========== ФУНКЦИИ АНАЛИЗА ВИДЕО ==========
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
                'bitrate': int(video_stream.get('bit_rate', 0)),
                'fps': eval(video_stream.get('r_frame_rate', '0/1')),
                'duration': float(info.get('format', {}).get('duration', 0))
            }
    except Exception as e:
        print(f"❌ Ошибка получения информации о видео: {e}")
    return None

# ========== ФУНКЦИИ АНАЛИЗА АУДИО ==========
def detect_beats(audio_path):
    """Определяет биты в аудиофайле с помощью librosa"""
    try:
        y, sr = librosa.load(audio_path, sr=None)
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
        beat_times = librosa.frames_to_time(beats, sr=sr)
        
        if len(beat_times) > 0 and beat_times[0] > 0.5:
            beat_times = np.insert(beat_times, 0, 0)
        
        print(f"🎵 Темп: {tempo:.1f} BPM, битов: {len(beat_times)}")
        return beat_times.tolist()
    except Exception as e:
        print(f"❌ Ошибка анализа аудио: {e}")
        return generate_fallback_beats(audio_path)

def generate_fallback_beats(audio_path):
    """Генерирует равномерную сетку битов, если анализ не удался"""
    try:
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
               '-of', 'default=noprint_wrappers=1:nokey=1', audio_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        duration = float(result.stdout.strip())
        
        beat_interval = 0.5
        beat_times = np.arange(0, duration, beat_interval).tolist()
        print(f"⚠️ Равномерная сетка: {len(beat_times)} битов")
        return beat_times
    except:
        return [0]

def get_optimal_bitrate(height, width):
    """Определяет оптимальный битрейт для заданного разрешения"""
    pixels = height * width
    if pixels >= 3840 * 2160:  # 4K
        return "25000k"
    elif pixels >= 2560 * 1440:  # 2K
        return "12000k"
    elif pixels >= 1920 * 1080:  # 1080p
        return "5000k"
    elif pixels >= 1280 * 720:  # 720p
        return "2500k"
    else:
        return "1000k"

def segment_video_by_beats(video_path, beat_times, output_dir, quality_key, multiplier=2):
    """Нарезает видео по битам с заданным качеством"""
    clips = []
    
    quality = QUALITY_PRESETS[quality_key]
    target_height = quality["height"]
    target_width = quality["width"]
    crf = quality["crf"]
    
    # Получаем информацию о видео
    video_info = get_video_info(video_path)
    if not video_info:
        return clips
    
    video_duration = video_info['duration']
    
    # Если исходное видео меньше целевого разрешения, используем оригинальное
    if video_info['height'] < target_height:
        target_height = video_info['height']
        target_width = video_info['width']
        print(f"📏 Сохраняю оригинальное разрешение: {target_height}p")
    
    # Группируем биты
    grouped_beats = []
    for i in range(0, len(beat_times) - 1, multiplier):
        start = beat_times[i]
        if i + multiplier < len(beat_times):
            end = beat_times[i + multiplier]
        else:
            end = beat_times[-1]
        
        if start < video_duration:
            grouped_beats.append((start, min(end, video_duration)))
    
    print(f"✂️ Нарезаю на {len(grouped_beats)} фрагментов ({target_height}p)")
    
    # Определяем аппаратное ускорение, если доступно
    hwaccel = []
    try:
        subprocess.run(['ffmpeg', '-hwaccels'], capture_output=True, text=True)
        hwaccel = ['-hwaccel', 'cuda']  # Для NVIDIA
    except:
        pass
    
    for i, (start, end) in enumerate(grouped_beats):
        duration = end - start
        if duration < 0.5:
            continue
            
        output_path = os.path.join(output_dir, f"clip_{i:03d}.mp4")
        
        # Команда с оптимизированными параметрами под качество
        cmd = [
            'ffmpeg', '-i', video_path,
            '-ss', str(start),
            '-t', str(duration),
            '-vf', f'scale={target_width}:{target_height}:flags=lanczos',
            '-c:v', 'libx264',
            '-preset', 'slow',  # Лучшее качество
            '-crf', str(crf),
            '-profile:v', 'high',
            '-level', '4.2' if target_height <= 1080 else '5.1',
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',
            '-an',  # без звука (добавим позже)
            '-y',
            output_path
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            clips.append(output_path)
        except subprocess.CalledProcessError as e:
            print(f"❌ Ошибка фрагмента {i}: {e}")
    
    return clips

def merge_clips_with_audio(clips, audio_path, output_path, quality_key):
    """Склеивает фрагменты и накладывает аудио с заданным качеством"""
    if not clips:
        return None
    
    quality = QUALITY_PRESETS[quality_key]
    
    # Создаём файл списка
    list_file = os.path.join(os.path.dirname(output_path), 'concat_list.txt')
    with open(list_file, 'w') as f:
        for clip in clips:
            f.write(f"file '{os.path.abspath(clip)}'\n")
    
    # Склеиваем видео
    temp_video = os.path.join(os.path.dirname(output_path), 'temp_merged.mp4')
    concat_cmd = [
        'ffmpeg', '-f', 'concat', '-safe', '0',
        '-i', list_file,
        '-c', 'copy',
        '-an',
        '-y',
        temp_video
    ]
    
    try:
        subprocess.run(concat_cmd, check=True, capture_output=True)
        
        # Накладываем аудио с качественным битрейтом
        final_cmd = [
            'ffmpeg', '-i', temp_video,
            '-i', audio_path,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-b:a', '320k',  # Высокое качество звука
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
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка склейки: {e}")
        return None

# ========== ФУНКЦИИ СКАЧИВАНИЯ ==========
async def download_video(url, quality_key):
    """Скачивает видео с YouTube в максимальном качестве"""
    temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
    
    quality = QUALITY_PRESETS[quality_key]
    target_height = quality["height"]
    
    # Выбираем формат в зависимости от нужного качества
    if target_height >= 2160:
        format_spec = 'bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/best[height<=2160][ext=mp4]'
    elif target_height >= 1440:
        format_spec = 'bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/best[height<=1440][ext=mp4]'
    elif target_height >= 1080:
        format_spec = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]'
    else:
        format_spec = f'bestvideo[height<={target_height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={target_height}][ext=mp4]'
    
    output = os.path.join(temp_dir, 'video.mp4')
    
    ydl_opts = {
        'format': format_spec,
        'outtmpl': output,
        'quiet': True,
        'merge_output_format': 'mp4',
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return output, info.get('title', 'video'), temp_dir
    except Exception as e:
        print(f"❌ Ошибка скачивания: {e}")
        shutil.rmtree(temp_dir)
        return None, None, None

# ========== КОМАНДЫ БОТА ==========
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("⚙️ Качество", callback_data="quality_menu"),
        InlineKeyboardButton("⏱️ Множитель", callback_data="multiplier_menu")
    )
    
    await message.reply(
        "🎬 **BeatSync 4K Bot**\n\n"
        "Я создаю идеальные эдиты под бит музыки!\n\n"
        "**Возможности:**\n"
        "• Поддержка 4K, 2K, 1080p, 720p\n"
        "• Анализ битов в реальном времени\n"
        "• Синхронная нарезка под ритм\n"
        "• Оптимизация под выбранное качество\n\n"
        "**Как пользоваться:**\n"
        "1️⃣ Установи качество и множитель\n"
        "2️⃣ Отправь видео (или ссылку YouTube)\n"
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
            f"✅ Качество установлено: {QUALITY_PRESETS[quality]['desc']}",
            parse_mode='Markdown'
        )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('set_multiplier_'))
async def set_multiplier(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    multiplier = int(callback.data.replace('set_multiplier_', ''))
    
    if 1 <= multiplier <= 5:
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]['multiplier'] = multiplier
        save_user_data()
        
        await callback.message.edit_text(
            f"✅ Множитель установлен: {multiplier}",
            parse_mode='Markdown'
        )
    await callback.answer()

# ========== ХРАНИЛИЩЕ ФАЙЛОВ ==========
user_videos = {}
user_audios = {}

# ========== ОБРАБОТЧИКИ КОНТЕНТА ==========
@dp.message_handler(content_types=['video', 'document'])
async def handle_video(message: types.Message):
    user_id = str(message.from_user.id)
    
    file_id = message.video.file_id if message.video else message.document.file_id
    file_size = message.video.file_size if message.video else message.document.file_size
    
    if file_size > MAX_FILE_SIZE:
        await message.reply(f"❌ Файл слишком большой (макс. {MAX_FILE_SIZE//1024//1024} MB)")
        return
    
    status = await message.reply("⏬ Скачиваю видео...")
    file = await bot.get_file(file_id)
    
    temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
    video_path = os.path.join(temp_dir, 'video.mp4')
    
    await bot.download_file(file.file_path, video_path)
    
    # Показываем информацию о видео
    video_info = get_video_info(video_path)
    if video_info:
        info_text = (
            f"📹 **Информация о видео:**\n"
            f"Разрешение: {video_info['width']}x{video_info['height']}\n"
            f"Длительность: {video_info['duration']:.1f} сек\n"
            f"FPS: {video_info['fps']:.2f}"
        )
        await message.reply(info_text, parse_mode='Markdown')
    
    if user_id not in user_videos:
        user_videos[user_id] = []
    user_videos[user_id].append({
        'path': video_path,
        'temp_dir': temp_dir
    })
    
    if user_id in user_audios and user_audios[user_id]:
        await status.edit_text("✅ Видео получено! Есть аудио, обрабатываю...")
        await process_user_files(message, user_id)
    else:
        await status.edit_text("✅ Видео получено! Теперь отправь аудио")

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
        await status.edit_text("✅ Аудио получено! Теперь отправь видео")

@dp.message_handler(content_types=['text'])
async def handle_youtube(message: types.Message):
    url = message.text.strip()
    
    if not url.startswith(('http://', 'https://')):
        await message.reply("❌ Отправь ссылку на YouTube или загрузи видеофайл")
        return
    
    user_id = str(message.from_user.id)
    quality = user_data.get(user_id, {}).get('quality', DEFAULT_QUALITY)
    
    status = await message.reply(f"⏬ Скачиваю видео с YouTube ({QUALITY_PRESETS[quality]['desc']})...")
    
    video_path, title, temp_dir = await download_video(url, quality)
    
    if not video_path:
        await status.edit_text("❌ Не удалось скачать видео")
        return
    
    video_info = get_video_info(video_path)
    if video_info:
        info_text = (
            f"📹 **Информация о видео:**\n"
            f"Разрешение: {video_info['width']}x{video_info['height']}\n"
            f"Длительность: {video_info['duration']:.1f} сек\n"
            f"FPS: {video_info['fps']:.2f}"
        )
        await message.reply(info_text, parse_mode='Markdown')
    
    if user_id not in user_videos:
        user_videos[user_id] = []
    user_videos[user_id].append({
        'path': video_path,
        'temp_dir': temp_dir
    })
    
    if user_id in user_audios and user_audios[user_id]:
        await status.edit_text("✅ Видео скачано! Есть аудио, обрабатываю...")
        await process_user_files(message, user_id)
    else:
        await status.edit_text("✅ Видео скачано! Теперь отправь аудио")

async def process_user_files(message: types.Message, user_id: str):
    """Обрабатывает пару видео+аудио"""
    
    video_info = user_videos[user_id][-1]
    audio_info = user_audios[user_id][-1]
    
    video_path = video_info['path']
    audio_path = audio_info['path']
    
    quality = user_data.get(user_id, {}).get('quality', DEFAULT_QUALITY)
    multiplier = user_data.get(user_id, {}).get('multiplier', 2)
    
    status = await message.reply(f"🎵 Анализирую биты в музыке...")
    
    beat_times = detect_beats(audio_path)
    
    if len(beat_times) < 2:
        await status.edit_text("❌ Не удалось определить биты в музыке")
        shutil.rmtree(video_info['temp_dir'])
        shutil.rmtree(audio_info['temp_dir'])
      
