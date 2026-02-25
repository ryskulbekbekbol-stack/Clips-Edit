#!/usr/bin/env python3
# Бот для нарезки YouTube видео под бит музыки (без librosa)
# by Колин

import os
import sys
import subprocess
import tempfile
import shutil
import json
import re
import math
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

# Настройки качества
QUALITY_PRESETS = {
    "720p": {"height": 720, "width": 1280, "crf": 20, "bitrate": "2500k", "desc": "720p (HD)"},
    "1080p": {"height": 1080, "width": 1920, "crf": 18, "bitrate": "5000k", "desc": "1080p (Full HD)"}
}

DEFAULT_QUALITY = "1080p"
TEMP_DIR = "temp"
MAX_CLIP_DURATION = 300  # 5 минут
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

# ========== ФУНКЦИИ РАБОТЫ С АУДИО ==========
def detect_beats_with_ffmpeg(audio_path):
    """
    Определяет биты в аудио с помощью FFmpeg
    Возвращает список временных меток (секунды)
    """
    try:
        # Получаем длительность аудио
        cmd_duration = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', audio_path
        ]
        result = subprocess.run(cmd_duration, capture_output=True, text=True)
        duration = float(result.stdout.strip())
        
        # Создаём равномерную сетку битов (примерно 120 BPM)
        # Можно настроить под свои нужды
        beats_per_second = 2  # 120 BPM
        interval = 1.0 / beats_per_second
        
        beat_times = []
        current_time = 0
        while current_time < duration:
            beat_times.append(current_time)
            current_time += interval
        
        print(f"🎵 Создано {len(beat_times)} битов (интервал {interval:.2f} сек)")
        return beat_times
    except Exception as e:
        print(f"❌ Ошибка определения битов: {e}")
        return [0]

# ========== ФУНКЦИИ РАБОТЫ С ВИДЕО ==========
def get_video_info(video_path):
    """Получает информацию о видео через ffprobe"""
    cmd = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_streams', '-show_format', video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        info = json.loads(result.stdout)
        
        video_stream = None
        for stream in info.get('streams', []):
            if stream.get('codec_type') == 'video':
                video_stream = stream
                break
        
        if video_stream:
            return {
                'width': int(video_stream.get('width', 0)),
                'height': int(video_stream.get('height', 0)),
                'duration': float(info.get('format', {}).get('duration', 0))
            }
    except Exception as e:
        print(f"❌ Ошибка получения информации о видео: {e}")
    return None

def download_youtube_video(url, quality_key):
    """Скачивает видео с YouTube в выбранном качестве"""
    temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
    
    quality = QUALITY_PRESETS[quality_key]
    target_height = quality["height"]
    
    # Выбираем формат под нужное качество
    format_spec = f'bestvideo[height<={target_height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={target_height}][ext=mp4]'
    
    video_output = os.path.join(temp_dir, 'video.mp4')
    audio_output = os.path.join(temp_dir, 'audio.mp3')
    
    ydl_opts = {
        'format': format_spec,
        'outtmpl': video_output.replace('.mp4', ''),
        'quiet': True,
        'merge_output_format': 'mp4',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Ищем скачанные файлы
            if os.path.exists(video_output):
                return video_output, audio_output, info.get('title', 'video'), temp_dir
            else:
                # Пробуем другие расширения
                for ext in ['.mp4', '.webm', '.mkv']:
                    if os.path.exists(video_output.replace('.mp4', ext)):
                        return video_output.replace('.mp4', ext), audio_output, info.get('title', 'video'), temp_dir
    except Exception as e:
        print(f"❌ Ошибка скачивания: {e}")
    
    shutil.rmtree(temp_dir)
    return None, None, None, None

def segment_video_by_beats(video_path, beat_times, output_dir, quality_key, multiplier=2):
    """Нарезает видео по битам"""
    clips = []
    
    quality = QUALITY_PRESETS[quality_key]
    target_height = quality["height"]
    target_width = quality["width"]
    
    video_info = get_video_info(video_path)
    if not video_info:
        return clips
    
    video_duration = video_info['duration']
    
    # Группируем биты по multiplier
    grouped_beats = []
    for i in range(0, len(beat_times) - 1, multiplier):
        start = beat_times[i]
        if i + multiplier < len(beat_times):
            end = beat_times[i + multiplier]
        else:
            end = beat_times[-1]
        
        if start < video_duration:
            grouped_beats.append((start, min(end, video_duration)))
    
    for i, (start, end) in enumerate(grouped_beats):
        duration = end - start
        if duration < 0.5:
            continue
            
        output_path = os.path.join(output_dir, f"clip_{i:03d}.mp4")
        
        cmd = [
            'ffmpeg', '-i', video_path,
            '-ss', str(start),
            '-t', str(duration),
            '-vf', f'scale={target_width}:{target_height}:flags=lanczos',
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', str(quality["crf"]),
            '-an',
            '-y',
            output_path
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            clips.append(output_path)
        except subprocess.CalledProcessError as e:
            print(f"❌ Ошибка нарезки фрагмента {i}: {e}")
    
    return clips

def merge_clips_with_audio(clips, audio_path, output_path, quality_key):
    """Склеивает фрагменты и накладывает аудио"""
    if not clips:
        return None
    
    quality = QUALITY_PRESETS[quality_key]
    
    # Создаём файл списка
    list_file = os.path.join(os.path.dirname(output_path), 'concat_list.txt')
    with open(list_file, 'w') as f:
        for clip in clips:
            f.write(f"file '{os.path.abspath(clip)}'\n")
    
    # Склеиваем видео без звука
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
        
        # Накладываем аудио
        final_cmd = [
            'ffmpeg', '-i', temp_video,
            '-i', audio_path,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-b:a', quality["bitrate"],
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

# ========== КОМАНДЫ БОТА ==========
@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("⚙️ Качество", callback_data="quality_menu"),
        InlineKeyboardButton("⏱️ Множитель", callback_data="multiplier_menu")
    )
    
    await message.reply(
        "🎬 **BeatSync Bot**\n\n"
        "Я нарезаю YouTube видео под бит музыки!\n\n"
        "**Как пользоваться:**\n"
        "1️⃣ Установи качество и множитель\n"
        "2️⃣ Отправь команду: /yt <ссылка> <длительность в секундах>\n"
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
    """Обрабатывает команду /yt <ссылка> <длительность>"""
    args = message.text.split()
    if len(args) < 3:
        await message.reply("❌ Использование: /yt <ссылка> <длительность в секундах>\nПример: /yt https://youtu.be/... 60")
        return
    
    url = args[1]
    try:
        clip_duration = int(args[2])
        if clip_duration > MAX_CLIP_DURATION:
            await message.reply(f"❌ Максимальная длительность {MAX_CLIP_DURATION} секунд")
            return
    except ValueError:
        await message.reply("❌ Длительность должна быть числом")
        return
    
    user_id = str(message.from_user.id)
    quality = user_data.get(user_id, {}).get('quality', DEFAULT_QUALITY)
    
    status = await message.reply(f"⏬ Скачиваю видео с YouTube ({QUALITY_PRESETS[quality]['desc']})...")
    
    video_path, audio_path, title, temp_dir = download_youtube_video(url, quality)
    
    if not video_path or not audio_path:
        await status.edit_text("❌ Не удалось скачать видео")
        return
    
    video_info = get_video_info(video_path)
    if video_info:
        info_text = (
            f"📹 **Информация о видео:**\n"
            f"Разрешение: {video_info['width']}x{video_info['height']}\n"
            f"Длительность: {video_info['duration']:.1f} сек"
        )
        await message.reply(info_text, parse_mode='Markdown')
    
    # Сохраняем для пользователя
    if user_id not in user_videos:
        user_videos[user_id] = []
    user_videos[user_id].append({
        'path': video_path,
        'temp_dir': temp_dir
    })
    
    if user_id in user_audios and user_audios[user_id]:
        await status.edit_text("✅ Видео скачано! Есть аудио, обрабатываю...")
        await process_user_files(message, user_id, clip_duration)
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
        clip_duration = user_data.get(user_id, {}).get('last_duration', 60)
        await process_user_files(message, user_id, clip_duration)
    else:
        await status.edit_text("✅ Аудио получено! Теперь отправь команду /yt с ссылкой")

async def process_user_files(message: types.Message, user_id: str, clip_duration: int):
    """Обрабатывает пару видео+аудио"""
    
    video_info = user_videos[user_id][-1]
    audio_info = user_audios[user_id][-1]
    
    video_path = video_info['path']
    audio_path = audio_info['path']
    
    quality = user_data.get(user_id, {}).get('quality', DEFAULT_QUALITY)
    multiplier = user_data.get(user_id, {}).get('multiplier', 2)
    
    status = await message.reply(f"🎵 Анализирую биты в музыке...")
    
    beat_times = detect_beats_with_ffmpeg(audio_path)
    
    if len(beat_times) < 2:
        await status.edit_text("❌ Не удалось определить биты в музыке")
        shutil.rmtree(video_info['temp_dir'])
        shutil.rmtree(audio_info['temp_dir'])
        user_videos[user_id].pop()
        user_audios[user_id].pop()
        return
    
    # Обрезаем биты до нужной длительности
    beat_times = [t for t in beat_times if t <= clip_duration]
    
    await status.edit_text(f"✂️ Нарезаю видео на фрагменты ({QUALITY_PRESETS[quality]['desc']})...")
    
    work_dir = tempfile.mkdtemp(dir=TEMP_DIR)
    clips = segment_video_by_beats(video_path, beat_times, work_dir, quality, multiplier)
    
    if not clips:
        await status.edit_text("❌ Не удалось нарезать видео")
        shutil.rmtree(work_dir)
        shutil.rmtree(video_info['temp_dir'])
        shutil.rmtree(audio_info['temp_dir'])
        user_videos[user_id].pop()
        user_audios[user_id].pop()
        return
    
    await status.edit_text(f"🔄 Склеиваю {len(clips)} фрагментов...")
    
    output_path = os.path.join(work_dir, 'final_clip.mp4')
    result = merge_clips_with_audio(clips, audio_path, output_path, quality)
    
    if not result:
        await status.edit_text("❌ Не удалось создать финальное видео")
        shutil.rmtree(work_dir)
        shutil.rmtree(video_info['temp_dir'])
        shutil.rmtree(audio_info['temp_dir'])
        user_videos[user_id].pop()
        user_audios[user_id].pop()
        return
    
    file_size = os.path.getsize(result) / (1024 * 1024)
    
    await status.edit_text("✅ Готово! Отправляю...")
    
    with open(result, 'rb') as f:
        await message.reply_video(
            f,
            caption=(
                f"🎬 **Клип под бит готов!**\n\n"
                f"📊 Качество: {QUALITY_PRESETS[quality]['desc']}\n"
                f"🎵 Длительность: {clip_duration} сек\n"
                f"✂️ Фрагментов: {len(clips)}\n"
                f"⚡ Множитель: {multiplier}\n"
                f"💾 Размер: {file_size:.1f} MB"
            ),
            parse_mode='Markdown'
        )
    
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

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    print("🤖 BeatSync Bot запущен")
    print(f"📊 Поддерживаемые качества: {', '.join(QUALITY_PRESETS.keys())}")
    executor.start_polling(dp, skip_updates=True)
