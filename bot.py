#!/usr/bin/env python3
# Бот для нарезки YouTube видео под бит музыки (4K)
# by Колин - ФИНАЛЬНАЯ ВЕРСИЯ

import os
import sys
import subprocess
import tempfile
import shutil
import json
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
    print("Ошибка: BOT_TOKEN не установлен!")
    sys.exit(1)

QUALITY_PRESETS = {
    "360p": {"height": 360, "width": 640, "crf": 23, "desc": "360p"},
    "480p": {"height": 480, "width": 854, "crf": 22, "desc": "480p"},
    "720p": {"height": 720, "width": 1280, "crf": 20, "desc": "720p"},
    "1080p": {"height": 1080, "width": 1920, "crf": 18, "desc": "1080p"},
    "1440p": {"height": 1440, "width": 2560, "crf": 16, "desc": "2K"},
    "2160p": {"height": 2160, "width": 3840, "crf": 14, "desc": "4K"}
}

DEFAULT_QUALITY = "1080p"
TEMP_DIR = "temp"
# ================================

os.makedirs(TEMP_DIR, exist_ok=True)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

user_data = {}
user_videos = {}
user_audios = {}

def load_user_data():
    global user_data
    try:
        with open('user_data.json', 'r') as f:
            user_data = json.load(f)
    except:
        user_data = {}

def save_user_data():
    with open('user_data.json', 'w') as f:
        json.dump(user_data, f)

load_user_data()

# ========== ФУНКЦИИ ==========
def download_youtube_video(url, quality_key):
    temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
    quality = QUALITY_PRESETS[quality_key]
    target_height = quality["height"]
    
    video_output = os.path.join(temp_dir, 'video.%(ext)s')
    
    ydl_opts = {
        'format': f'bestvideo[height<={target_height}]+bestaudio/best[height<={target_height}]',
        'outtmpl': video_output,
        'merge_output_format': 'mp4',
        'quiet': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web', 'ios']
            }
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            base = filename.rsplit('.', 1)[0]
            
            if os.path.exists(base + '.mp4'):
                return base + '.mp4', info.get('title', 'video'), temp_dir
    except:
        pass
    
    shutil.rmtree(temp_dir)
    return None, None, None

def get_video_info(video_path):
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        duration = float(result.stdout.strip())
        return {'duration': duration}
    except:
        return None

def detect_beats(audio_path):
    try:
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', audio_path]
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

def cut_video(video_path, start, end, output_path, quality_key):
    quality = QUALITY_PRESETS[quality_key]
    cmd = [
        'ffmpeg', '-i', video_path,
        '-ss', str(start),
        '-to', str(end),
        '-vf', f'scale={quality["width"]}:{quality["height"]}',
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', str(quality["crf"]),
        '-an', '-y',
        output_path
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except:
        return False

def merge_videos(video_list, audio_path, output_path):
    if not video_list:
        return None
    
    list_file = os.path.join(os.path.dirname(output_path), 'list.txt')
    with open(list_file, 'w') as f:
        for v in video_list:
            f.write(f"file '{v}'\n")
    
    temp_video = os.path.join(os.path.dirname(output_path), 'merged.mp4')
    concat_cmd = ['ffmpeg', '-f', 'concat', '-safe', '0', '-i', list_file, '-c', 'copy', '-y', temp_video]
    
    try:
        subprocess.run(concat_cmd, check=True, capture_output=True)
        final_cmd = ['ffmpeg', '-i', temp_video, '-i', audio_path, '-c:v', 'copy', '-c:a', 'aac', '-map', '0:v:0', '-map', '1:a:0', '-shortest', '-y', output_path]
        subprocess.run(final_cmd, check=True, capture_output=True)
        os.remove(temp_video)
        os.remove(list_file)
        return output_path
    except:
        return None

# ========== КОМАНДЫ ==========
@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("Качество", callback_data="quality_menu"),
        InlineKeyboardButton("Множитель", callback_data="multiplier_menu")
    )
    await message.reply(
        "🎬 **BeatSync 4K Bot**\n\n"
        "1. /quality - выбрать качество\n"
        "2. /multiplier - множитель\n"
        "3. /yt <ссылка> - скачать видео\n"
        "4. Отправить аудио",
        reply_markup=markup
    )

@dp.message_handler(commands=['quality'])
async def quality_cmd(message: types.Message):
    user_id = str(message.from_user.id)
    current = user_data.get(user_id, {}).get('quality', DEFAULT_QUALITY)
    markup = InlineKeyboardMarkup(row_width=2)
    for key, preset in QUALITY_PRESETS.items():
        text = f"✅ {preset['desc']}" if key == current else preset['desc']
        markup.add(InlineKeyboardButton(text, callback_data=f"setq_{key}"))
    await message.reply("Выбери качество:", reply_markup=markup)

@dp.message_handler(commands=['multiplier'])
async def multiplier_cmd(message: types.Message):
    user_id = str(message.from_user.id)
    current = user_data.get(user_id, {}).get('multiplier', 2)
    markup = InlineKeyboardMarkup(row_width=5)
    row = []
    for i in range(1, 6):
        text = f"✅{i}" if i == current else str(i)
        row.append(InlineKeyboardButton(text, callback_data=f"setm_{i}"))
    markup.row(*row)
    await message.reply("Выбери множитель:", reply_markup=markup)

@dp.message_handler(commands=['settings'])
async def settings_cmd(message: types.Message):
    user_id = str(message.from_user.id)
    quality = user_data.get(user_id, {}).get('quality', DEFAULT_QUALITY)
    multiplier = user_data.get(user_id, {}).get('multiplier', 2)
    await message.reply(
        f"⚙️ Настройки\n"
        f"Качество: {QUALITY_PRESETS[quality]['desc']}\n"
        f"Множитель: {multiplier}"
    )

@dp.message_handler(commands=['yt'])
async def yt_command(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply("❌ Использование: /yt <ссылка>")
        return
    
    url = args[1]
    user_id = str(message.from_user.id)
    quality = user_data.get(user_id, {}).get('quality', DEFAULT_QUALITY)
    
    msg = await message.reply(f"⏬ Скачиваю видео...")
    video_path, title, temp_dir = download_youtube_video(url, quality)
    
    if not video_path:
        await msg.edit_text("❌ Не удалось скачать видео")
        return
    
    info = get_video_info(video_path)
    if info:
        await message.reply(f"✅ Видео скачано!\nДлительность: {info['duration']:.1f} сек")
    
    if user_id not in user_videos:
        user_videos[user_id] = []
    user_videos[user_id].append({'path': video_path, 'temp_dir': temp_dir})
    
    if user_id in user_audios and user_audios[user_id]:
        await msg.edit_text("✅ Видео есть! Обрабатываю...")
        await process_files(message, user_id)
    else:
        await msg.edit_text("✅ Видео скачано! Теперь отправь аудио")

@dp.message_handler(content_types=['audio'])
async def handle_audio(message: types.Message):
    user_id = str(message.from_user.id)
    msg = await message.reply("⏬ Скачиваю аудио...")
    file = await bot.get_file(message.audio.file_id)
    temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
    audio_path = os.path.join(temp_dir, 'audio.mp3')
    await bot.download_file(file.file_path, audio_path)
    
    if user_id not in user_audios:
        user_audios[user_id] = []
    user_audios[user_id].append({'path': audio_path, 'temp_dir': temp_dir})
    
    if user_id in user_videos and user_videos[user_id]:
        await msg.edit_text("✅ Аудио есть! Обрабатываю...")
        await process_files(message, user_id)
    else:
        await msg.edit_text("✅ Аудио скачано! Теперь отправь /yt с ссылкой")

async def process_files(message: types.Message, user_id: str):
    video_info = user_videos[user_id][-1]
    audio_info = user_audios[user_id][-1]
    
    video_path = video_info['path']
    audio_path = audio_info['path']
    
    quality = user_data.get(user_id, {}).get('quality', DEFAULT_QUALITY)
    multiplier = user_data.get(user_id, {}).get('multiplier', 2)
    
    msg = await message.reply(f"🎵 Анализирую биты...")
    beats = detect_beats(audio_path)
    
    if len(beats) < 2:
        await msg.edit_text("❌ Не удалось определить биты")
        return
    
    video_info_data = get_video_info(video_path)
    if not video_info_data:
        await msg.edit_text("❌ Ошибка видео")
        return
    
    video_duration = video_info_data['duration']
    beats = [b for b in beats if b < video_duration]
    
    if len(beats) < 2:
        await msg.edit_text("❌ Видео слишком короткое")
        return
    
    await msg.edit_text(f"✂️ Нарезаю видео...")
    work_dir = tempfile.mkdtemp(dir=TEMP_DIR)
    clip_paths = []
    
    for i in range(0, len(beats)-1, multiplier):
        start = beats[i]
        end = beats[i+multiplier] if i+multiplier < len(beats) else beats[-1]
        if end - start < 0.5:
            continue
        clip_path = os.path.join(work_dir, f"clip_{i:03d}.mp4")
        if cut_video(video_path, start, end, clip_path, quality):
            clip_paths.append(clip_path)
    
    if not clip_paths:
        await msg.edit_text("❌ Не удалось нарезать видео")
        return
    
    await msg.edit_text(f"🔄 Склеиваю {len(clip_paths)} фрагментов...")
    output_path = os.path.join(work_dir, 'final.mp4')
    result = merge_videos(clip_paths, audio_path, output_path)
    
    if not result:
        await msg.edit_text("❌ Не удалось склеить видео")
        return
    
    file_size = os.path.getsize(result) / 1024 / 1024
    
    await msg.edit_text("✅ Готово! Отправляю...")
    with open(result, 'rb') as f:
        await message.reply_video(
            f,
            caption=f"🎬 Готово!\nКачество: {QUALITY_PRESETS[quality]['desc']}\nФрагментов: {len(clip_paths)}"
        )
    
    shutil.rmtree(work_dir)
    shutil.rmtree(video_info['temp_dir'])
    shutil.rmtree(audio_info['temp_dir'])
    user_videos[user_id].pop()
    user_audios[user_id].pop()

# ========== CALLBACKS ==========
@dp.callback_query_handler(lambda c: c.data == 'quality_menu')
async def quality_menu(callback: types.CallbackQuery):
    await quality_cmd(callback.message)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'multiplier_menu')
async def multiplier_menu(callback: types.CallbackQuery):
    await multiplier_cmd(callback.message)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('setq_'))
async def set_quality(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    quality = callback.data.replace('setq_', '')
    if quality in QUALITY_PRESETS:
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]['quality'] = quality
        save_user_data()
        await callback.message.edit_text(f"✅ Качество: {QUALITY_PRESETS[quality]['desc']}")
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('setm_'))
async def set_multiplier(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    multiplier = int(callback.data.replace('setm_', ''))
    if 1 <= multiplier <= 5:
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]['multiplier'] = multiplier
        save_user_data()
        await callback.message.edit_text(f"✅ Множитель: {multiplier}")
    await callback.answer()

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    print("🤖 BeatSync Bot запущен")
    executor.start_polling(dp, skip_updates=True)
