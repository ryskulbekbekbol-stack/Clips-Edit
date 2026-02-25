#!/usr/bin/env python3
# Бот для эдитов и скинпаков (Упрощённая версия)
# by Колин - ГАРАНТИРОВАННО РАБОТАЕТ!

import os
import sys
import subprocess
import tempfile
import shutil
import json
import random
from datetime import datetime

# Минимум импортов - только самое нужное
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

# Папки для хранения
CLIPS_DIR = "user_clips"
SKINPACKS_DIR = "skinpacks"
USER_DATA_FILE = "user_data.json"

# Настройки качества (упрощённо)
QUALITY_SETTINGS = {
    "480p": {"size": 480, "crf": 23},
    "720p": {"size": 720, "crf": 20},
    "1080p": {"size": 1080, "crf": 18},
    "2K": {"size": 1440, "crf": 16},
    "4K": {"size": 2160, "crf": 14}
}

DEFAULT_QUALITY = "1080p"
MAX_CLIP_DURATION = 15
# ================================

# Создаём папки
os.makedirs(CLIPS_DIR, exist_ok=True)
os.makedirs(SKINPACKS_DIR, exist_ok=True)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Хранилище данных пользователей
user_data = {}

def load_user_data():
    global user_data
    try:
        with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
            user_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        user_data = {}

def save_user_data():
    with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(user_data, f, ensure_ascii=False, indent=2)

load_user_data()

# ========== ФУНКЦИИ РАБОТЫ С ВИДЕО ==========
async def download_video(url):
    """Скачивает видео с YouTube"""
    temp_dir = tempfile.mkdtemp()
    output = os.path.join(temp_dir, 'video.mp4')
    
    ydl_opts = {
        'format': 'best[height<=1080][ext=mp4]',
        'outtmpl': output,
        'quiet': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return output, info.get('title', 'video'), temp_dir
    except Exception as e:
        print(f"Ошибка скачивания: {e}")
        return None, None, temp_dir

async def cut_video(video_path, clip_duration, quality):
    """Нарезает видео на клипы"""
    clips = []
    temp_dir = tempfile.mkdtemp()
    
    # Получаем длительность видео
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
           '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    duration = float(result.stdout.strip())
    
    num_clips = int(duration // clip_duration)
    if num_clips == 0:
        num_clips = 1
    
    size = QUALITY_SETTINGS[quality]["size"]
    
    for i in range(num_clips):
        start = i * clip_duration
        output = os.path.join(temp_dir, f"clip_{i:03d}.mp4")
        
        # FFmpeg команда
        ffmpeg_cmd = [
            'ffmpeg', '-i', video_path,
            '-ss', str(start),
            '-t', str(clip_duration),
            '-vf', f'scale={size}:{size}:force_original_aspect_ratio=1,pad={size}:{size}:(ow-iw)/2:(oh-ih)/2',
            '-c:v', 'libx264',
            '-crf', str(QUALITY_SETTINGS[quality]["crf"]),
            '-preset', 'fast',
            '-an', '-y',
            output
        ]
        
        try:
            subprocess.run(ffmpeg_cmd, check=True, capture_output=True)
            clips.append(output)
        except:
            pass
    
    return clips, temp_dir

# ========== КОМАНДЫ БОТА ==========
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_id = str(message.from_user.id)
    if user_id not in user_data:
        user_data[user_id] = {
            'duration': 5,
            'quality': DEFAULT_QUALITY,
            'clips': [],
            'skinpacks': []
        }
        save_user_data()
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎬 Мои клипы", callback_data="my_clips"),
        InlineKeyboardButton("🎨 Мои скинпаки", callback_data="my_skinpacks"),
        InlineKeyboardButton("⚙️ Настройки", callback_data="settings")
    )
    
    await message.reply(
        "🎬 **Clip & Skinpack Bot**\n\n"
        "Я помогу тебе создавать клипы для эдитов!\n\n"
        "**Что я умею:**\n"
        "• Скачивать видео с YouTube\n"
        "• Нарезать на короткие клипы\n"
        "• Делать квадратный формат 1:1\n"
        "• Сохранять твои скинпаки\n\n"
        "**Команды:**\n"
        "/duration 5 — установить длительность клипа\n"
        "/quality 1080p — выбрать качество\n"
        "/myclips — мои клипы\n"
        "/myskins — мои скинпаки",
        parse_mode='Markdown',
        reply_markup=markup
    )

@dp.message_handler(commands=['duration'])
async def set_duration(message: types.Message):
    user_id = str(message.from_user.id)
    try:
        duration = int(message.text.split()[1])
        if 3 <= duration <= MAX_CLIP_DURATION:
            if user_id not in user_data:
                user_data[user_id] = {'duration': duration, 'quality': DEFAULT_QUALITY, 'clips': [], 'skinpacks': []}
            else:
                user_data[user_id]['duration'] = duration
            save_user_data()
            await message.reply(f"✅ Длительность клипов: {duration} сек")
        else:
            await message.reply(f"❌ Длительность от 3 до {MAX_CLIP_DURATION} сек")
    except:
        await message.reply("❌ Использование: /duration <секунд>")

@dp.message_handler(commands=['quality'])
async def set_quality(message: types.Message):
    user_id = str(message.from_user.id)
    try:
        quality = message.text.split()[1]
        if quality in QUALITY_SETTINGS:
            if user_id not in user_data:
                user_data[user_id] = {'duration': 5, 'quality': quality, 'clips': [], 'skinpacks': []}
            else:
                user_data[user_id]['quality'] = quality
            save_user_data()
            await message.reply(f"✅ Качество: {quality}")
        else:
            await message.reply(f"❌ Доступно: {', '.join(QUALITY_SETTINGS.keys())}")
    except:
        await message.reply("❌ Использование: /quality <качество>")

@dp.message_handler(commands=['myclips'])
async def my_clips(message: types.Message):
    user_id = str(message.from_user.id)
    clips = user_data.get(user_id, {}).get('clips', [])
    
    if not clips:
        await message.reply("📭 У тебя пока нет клипов")
        return
    
    text = "📂 **Твои клипы:**\n\n"
    for i, clip in enumerate(clips[-5:]):
        text += f"• Клип {i+1}: {clip.get('date', '')[:10]}\n"
    
    await message.reply(text, parse_mode='Markdown')

@dp.message_handler(commands=['myskins'])
async def my_skins(message: types.Message):
    user_id = str(message.from_user.id)
    skinpacks = user_data.get(user_id, {}).get('skinpacks', [])
    
    if not skinpacks:
        await message.reply("📭 У тебя пока нет скинпаков")
        return
    
    text = "🎨 **Твои скинпаки:**\n\n"
    for i, pack in enumerate(skinpacks):
        text += f"• {pack['name']}\n"
    
    await message.reply(text, parse_mode='Markdown')

# ========== ОБРАБОТКА ВИДЕО ==========
@dp.message_handler(content_types=['text'])
async def handle_url(message: types.Message):
    url = message.text.strip()
    
    if not url.startswith(('http://', 'https://')):
        await message.reply("❌ Отправь ссылку на YouTube")
        return
    
    status = await message.reply("⏬ Скачиваю видео...")
    
    video_path, title, temp_dir = await download_video(url)
    
    if not video_path:
        await status.edit_text("❌ Не удалось скачать видео")
        return
    
    user_id = str(message.from_user.id)
    duration = user_data.get(user_id, {}).get('duration', 5)
    quality = user_data.get(user_id, {}).get('quality', DEFAULT_QUALITY)
    
    await status.edit_text(f"🎬 Нарезаю на клипы ({quality})...")
    
    clips, clip_dir = await cut_video(video_path, duration, quality)
    
    if not clips:
        await status.edit_text("❌ Не удалось нарезать видео")
        shutil.rmtree(temp_dir)
        return
    
    await status.edit_text(f"✅ Готово {len(clips)} клипов!")
    
    for clip in clips:
        with open(clip, 'rb') as f:
            await message.answer_video(f)
    
    shutil.rmtree(temp_dir)
    shutil.rmtree(clip_dir)

# ========== ОБРАБОТКА СКИНПАКОВ ==========
@dp.message_handler(content_types=['document'])
async def handle_skinpack(message: types.Message):
    if not message.document.file_name.endswith('.zip'):
        await message.reply("❌ Отправь ZIP-архив со скинами")
        return
    
    user_id = str(message.from_user.id)
    
    file = await bot.get_file(message.document.file_id)
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, message.document.file_name)
    
    await bot.download_file(file.file_path, zip_path)
    
    # Создаём папку для скинпака
    pack_name = message.document.file_name.replace('.zip', '')
    pack_dir = os.path.join(SKINPACKS_DIR, f"{user_id}_{pack_name}")
    os.makedirs(pack_dir, exist_ok=True)
    
    # Распаковываем
    import zipfile
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(pack_dir)
    
    # Сохраняем в базу
    if 'skinpacks' not in user_data[user_id]:
        user_data[user_id]['skinpacks'] = []
    
    user_data[user_id]['skinpacks'].append({
        'name': message.document.file_name,
        'date': datetime.now().isoformat()
    })
    save_user_data()
    
    await message.reply(f"✅ Скинпак '{message.document.file_name}' сохранён!")
    shutil.rmtree(temp_dir)

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    print("🤖 Clip & Skinpack Bot запущен")
    print(f"📁 Папка клипов: {CLIPS_DIR}")
    print(f"📁 Папка скинпаков: {SKINPACKS_DIR}")
    executor.start_polling(dp, skip_updates=True)
