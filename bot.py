#!/usr/bin/env python3
# Бот для эдитов и скинпаков (формат 1:1 + 4К)
# by Колин (исправленная версия)

import os
import sys
import subprocess
import tempfile
import shutil
import json
import random
from pathlib import Path
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
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

# Настройки качества
QUALITY_PRESETS = {
    "SD": {"height": 480, "width": 480, "crf": 23, "desc": "480p"},
    "HD": {"height": 720, "width": 720, "crf": 20, "desc": "720p"},
    "FULL_HD": {"height": 1080, "width": 1080, "crf": 18, "desc": "1080p"},
    "2K": {"height": 1440, "width": 1440, "crf": 16, "desc": "2K"},
    "4K": {"height": 2160, "width": 2160, "crf": 14, "desc": "4K"}
}

DEFAULT_QUALITY = "FULL_HD"
MAX_CLIP_DURATION = 15
# ================================

# Создаём папки
os.makedirs(CLIPS_DIR, exist_ok=True)
os.makedirs(SKINPACKS_DIR, exist_ok=True)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

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
async def get_video_info(video_path):
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
                'fps': eval(video_stream.get('r_frame_rate', '0/1')),
                'duration': float(info.get('format', {}).get('duration', 0))
            }
    except Exception as e:
        print(f"Ошибка получения информации о видео: {e}")
    return None

async def download_video(url):
    """Скачивает видео в максимальном качестве"""
    temp_dir = tempfile.mkdtemp()
    output_template = os.path.join(temp_dir, '%(title)s.%(ext)s')
    
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4',
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            # Находим скачанный файл
            for ext in ['.mp4', '.webm', '.mkv']:
                if os.path.exists(filename + ext):
                    return filename + ext, info.get('title', 'video'), temp_dir
            return None, None, temp_dir
    except Exception as e:
        print(f"Ошибка скачивания: {e}")
        return None, None, temp_dir

async def convert_to_square(video_path, output_path, quality_key):
    """Конвертирует видео в квадратный формат 1:1 с выбранным качеством"""
    quality = QUALITY_PRESETS.get(quality_key, QUALITY_PRESETS[DEFAULT_QUALITY])
    
    video_info = await get_video_info(video_path)
    
    target_size = quality['height']
    crf_value = quality['crf']
    
    if video_info and video_info['height'] < target_size:
        target_size = video_info['height']
        print(f"Исходное видео {video_info['height']}p, сохраняем оригинальное качество")
    
    cmd = [
        'ffmpeg', '-i', video_path,
        '-vf', (
            f'scale={target_size}:{target_size}:force_original_aspect_ratio=1,'
            f'pad={target_size}:{target_size}:(ow-iw)/2:(oh-ih)/2,'
            f'setsar=1,fps=30'
        ),
        '-c:v', 'libx264',
        '-preset', 'slow',
        '-crf', str(crf_value),
        '-profile:v', 'high',
        '-level', '4.2',
        '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart',
        '-an',
        '-y',
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Ошибка конвертации: {e}")
        return False

async def cut_into_clips(video_path, clip_duration, quality_key):
    """Нарезает видео на клипы"""
    clips = []
    temp_dir = tempfile.mkdtemp()
    
    video_info = await get_video_info(video_path)
    if not video_info:
        return clips, temp_dir
    
    duration = video_info['duration']
    
    num_clips = int(duration // clip_duration)
    if num_clips == 0:
        num_clips = 1
    
    for i in range(num_clips):
        start_time = i * clip_duration
        temp_clip = os.path.join(temp_dir, f"temp_{i:03d}.mp4")
        output_path = os.path.join(temp_dir, f"clip_{i:03d}.mp4")
        
        cut_cmd = [
            'ffmpeg', '-i', video_path,
            '-ss', str(start_time),
            '-t', str(clip_duration),
            '-c', 'copy',
            '-avoid_negative_ts', 'make_zero',
            '-y',
            temp_clip
        ]
        
        try:
            subprocess.run(cut_cmd, check=True, capture_output=True)
            
            if await convert_to_square(temp_clip, output_path, quality_key):
                clips.append(output_path)
            
            os.remove(temp_clip)
        except subprocess.CalledProcessError as e:
            print(f"Ошибка нарезки: {e}")
    
    return clips, temp_dir

async def process_skinpack(message: types.Message, file_path: str, filename: str):
    """Обрабатывает загруженный скинпак"""
    user_id = str(message.from_user.id)
    
    skinpack_name = filename.replace('.', '_')
    skinpack_dir = os.path.join(SKINPACKS_DIR, f"{user_id}_{skinpack_name}")
    os.makedirs(skinpack_dir, exist_ok=True)
    
    if filename.endswith('.zip'):
        import zipfile
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            zip_ref.extractall(skinpack_dir)
    else:
        shutil.copy(file_path, os.path.join(skinpack_dir, filename))
    
    if 'skinpacks' not in user_data[user_id]:
        user_data[user_id]['skinpacks'] = []
    
    user_data[user_id]['skinpacks'].append({
        'name': filename,
        'path': skinpack_dir,
        'date': datetime.now().isoformat()
    })
    save_user_data()
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("👀 Посмотреть скины", callback_data=f"view_skinpack_{len(user_data[user_id]['skinpacks'])-1}"),
        InlineKeyboardButton("📋 Мои скинпаки", callback_data="my_skinpacks")
    )
    
    await message.reply(f"✅ Скинпак '{filename}' успешно загружен!", reply_markup=markup)

async def process_video(message: types.Message, video_path: str, original_name: str, is_user_clip=False):
    """Обрабатывает видео: нарезает на квадратные клипы"""
    user_id = str(message.from_user.id)
    clip_duration = user_data.get(user_id, {}).get('duration', 5)
    quality = user_data.get(user_id, {}).get('quality', DEFAULT_QUALITY)
    
    status_msg = await message.reply(f"🎬 Начинаю нарезку на клипы (качество: {QUALITY_PRESETS[quality]['desc']})...")
    
    clips, temp_dir = await cut_into_clips(video_path, clip_duration, quality)
    
    if not clips:
        await status_msg.edit_text("❌ Не удалось нарезать видео")
        return
    
    await status_msg.edit_text(f"✅ Готово {len(clips)} клипов! Отправляю...")
    
    if is_user_clip:
        if 'clips' not in user_data[user_id]:
            user_data[user_id]['clips'] = []
        
        for clip_path in clips:
            clip_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000,9999)}.mp4"
            dest_path = os.path.join(CLIPS_DIR, f"{user_id}_{clip_name}")
            shutil.copy(clip_path, dest_path)
            user_data[user_id]['clips'].append({
                'path': dest_path,
                'name': clip_name,
                'date': datetime.now().isoformat(),
                'quality': quality
            })
        save_user_data()
    
    for i, clip_path in enumerate(clips):
        with open(clip_path, 'rb') as f:
            caption = f"🎬 Клип {i+1}/{len(clips)} из {original_name}\n📐 Формат 1:1\n📊 Качество: {QUALITY_PRESETS[quality]['desc']}"
            await message.answer_video(
                f,
                caption=caption,
                supports_streaming=True
            )
    
    shutil.rmtree(temp_dir)

# ========== КОМАНДЫ БОТА ==========
@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    user_id = str(message.from_user.id)
    if user_id not in user_data:
        user_data[user_id] = {
            'duration': 5,
            'quality': DEFAULT_QUALITY,
            'clips': [],
            'skinpacks': [],
            'skins': []
        }
        save_user_data()
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎬 Мои клипы", callback_data="my_clips"),
        InlineKeyboardButton("🎨 Мои скинпаки", callback_data="my_skinpacks"),
        InlineKeyboardButton("⚙️ Настройки", callback_data="settings"),
        InlineKeyboardButton("📊 Качество", callback_data="quality_menu")
    )
    
    await message.reply(
        "🎬 **Clip & Skinpack Bot (4K Ready)**\n\n"
        "Я помогу тебе создавать крутые клипы в высоком качестве!\n\n"
        "**Доступные качества:**\n"
        "• 480p (SD)\n"
        "• 720p (HD)\n"
        "• 1080p (Full HD)\n"
        "• 2K (1440p)\n"
        "• 4K (2160p)\n\n"
        "**Команды:**\n"
        "/duration <сек> — установить длительность клипа\n"
        "/quality — выбрать качество\n"
        "/myclips — мои сохранённые клипы\n"
        "/myskins — мои скинпаки",
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
        f"📊 **Выбери качество видео**\n\nТекущее: {QUALITY_PRESETS[current]['desc']}",
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
                user_data[user_id] = {'duration': duration, 'quality': DEFAULT_QUALITY, 'clips': [], 'skinpacks': [], 'skins': []}
            else:
                user_data[user_id]['duration'] = duration
            save_user_data()
            await message.reply(f"✅ Длительность клипов установлена: {duration} сек")
        else:
            await message.reply(f"❌ Длительность должна быть от 3 до {MAX_CLIP_DURATION} секунд")
    except (IndexError, ValueError):
        await message.reply(f"❌ Использование: /duration <секунд>")

@dp.message_handler(commands=['myclips'])
async def my_clips_cmd(message: types.Message):
    user_id = str(message.from_user.id)
    clips = user_data.get(user_id, {}).get('clips', [])
    
    if not clips:
        await message.reply("📭 У тебя пока нет сохранённых клипов")
        return
    
    markup = InlineKeyboardMarkup(row_width=1)
    for i, clip in enumerate(clips[-10:]):
        quality = clip.get('quality', 'unknown')
        quality_desc = QUALITY_PRESETS.get(quality, {}).get('desc', quality)
        markup.add(InlineKeyboardButton(
            f"🎬 Клип {i+1} ({quality_desc})",
            callback_data=f"get_clip_{i}"
        ))
    
    await message.reply(f"📂 У тебя {len(clips)} сохранённых клипов", reply_markup=markup)

@dp.message_handler(commands=['myskins'])
async def my_skins_cmd(message: types.Message):
    user_id = str(message.from_user.id)
    skinpacks = user_data.get(user_id, {}).get('skinpacks', [])
    
    if not skinpacks:
        await message.reply("📭 У тебя пока нет скинпаков")
        return
    
    markup = InlineKeyboardMarkup(row_width=1)
    for i, skinpack in enumerate(skinpacks):
        markup.add(InlineKeyboardButton(f"🎨 {skinpack['name']}", callback_data=f"view_skinpack_{i}"))
    
    await message.reply(f"📂 У тебя {len(skinpacks)} скинпаков", reply_markup=markup)

# ========== ОБРАБОТЧИКИ КОНТЕНТА ==========
@dp.message_handler(content_types=['text'])
async def handle_url(message: types.Message):
    url = message.text.strip()
    
    if not url.startswith(('http://', 'https://')):
        await message.reply("❌ Отправь ссылку на видео или загрузи файл")
        return
    
    status_msg = await message.reply("⏬ Скачиваю видео...")
    
    video_path, title, temp_dir = await download_video(url)
    
    if not video_path:
        await status_msg.edit_text("❌ Не удалось скачать видео")
        return
    
    await status_msg.edit_text("✅ Видео скачано! Начинаю обработку...")
    await process_video(message, video_path, title)
    shutil.rmtree(temp_dir)

@dp.message_handler(content_types=['video', 'document'])
async def handle_video_file(message: types.Message):
    is_skinpack = False
    filename = ""
    
    if message.document:
        filename = message.document.file_name
        if filename and filename.endswith(('.zip', '.rar', '.7z', '.png', '.jpg')):
            is_skinpack = True
    
    file_id = message.video.file_id if message.video else message.document.file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path
    
    temp_dir = tempfile.mkdtemp()
    local_path = os.path.join(temp_dir, filename if filename else 'video.mp4')
    
    await bot.download_file(file_path, local_path)
    
    if is_skinpack:
        await process_skinpack(message, local_path, filename)
    else:
        video_info = await get_video_info(local_path)
        if video_info:
            quality_msg = f"📊 Исходное видео: {video_info['height']}p"
            if video_info['height'] >= 2160:
                quality_msg += " (4K доступно!)"
            await message.reply(quality_msg)
        
        await process_video(message, local_path, "загруженное видео", is_user_clip=True)
    
    shutil.rmtree(temp_dir)

@dp.message_handler(content_types=['photo'])
async def handle_skin_photo(message: types.Message):
    user_id = str(message.from_user.id)
    
    file_id = message.photo[-1].file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path
    
    temp_dir = tempfile.mkdtemp()
    local_path = os.path.join(temp_dir, f"skin_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
    
    await bot.download_file(file_path, local_path)
    
    if 'skins' not in user_data[user_id]:
        user_data[user_id]['skins'] = []
    
    skin_name = f"skin_{len(user_data[user_id].get('skins', [])) + 1}"
    user_data[user_id]['skins'].append({
        'name': skin_name,
        'path': local_path,
        'date': datetime.now().isoformat()
    })
    save_user_data()
    
    await message.reply(f"✅ Скин '{skin_name}' сохранён!")
    shutil.rmtree(temp_dir)

# ========== ОБРАБОТЧИКИ КНОПОК ==========
@dp.callback_query_handler(lambda c: c.data == 'my_clips')
async def my_clips_callback(callback: types.CallbackQuery):
    await my_clips_cmd(callback.message)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'my_skinpacks')
async def my_skinpacks_callback(callback: types.CallbackQuery):
    await my_skins_cmd(callback.message)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'settings')
async def settings_callback(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    duration = user_data.get(user_id, {}).get('duration', 5)
    quality = user_data.get(user_id, {}).get('quality', DEFAULT_QUALITY)
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎬 Мои клипы", callback_data="my_clips"),
        InlineKeyboardButton("🎨 Мои скинпаки", callback_data="my_skinpacks"),
        InlineKeyboardButton("📊 Качество", callback_data="quality_menu")
    )
    
    await callback.message.edit_text(
        f"⚙️ **Настройки**\n\n"
        f"Длительность клипов: {duration} сек\n"
        f"Формат видео: 1:1 (квадрат)\n"
        f"Качество: {QUALITY_PRESETS[quality]['desc']}\n\n"
        f"Изменить длительность: /duration <сек>\n"
        f"Изменить качество: /quality",
        parse_mode='Markdown',
        reply_markup=markup
    )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'quality_menu')
async def quality_menu_callback(callback: types.CallbackQuery):
    await quality_cmd(callback.message)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('set_quality_'))
async def set_quality_callback(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    quality = callback.data.replace('set_quality_', '')
    
    if quality in QUALITY_PRESETS:
        if user_id not in user_data:
            user_data[user_id] = {'duration': 5, 'quality': quality, 'clips': [], 'skinpacks': [], 'skins': []}
        else:
            user_data[user_id]['quality'] = quality
        save_user_data()
        
        await callback.message.edit_text(
            f"✅ Качество установлено: {QUALITY_PRESETS[quality]['desc']}\n\n"
            f"Теперь все новые клипы будут создаваться в этом качестве.",
            parse_mode='Markdown'
        )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('get_clip_'))
async def get_clip_callback(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    index = int(callback.data.split('_')[2])
    
    clips = user_data.get(user_id, {}).get('clips', [])
    if 0 <= index < len(clips):
        clip = clips[index]
        if os.path.exists(clip['path']):
            with open(clip['path'], 'rb') as f:
                quality = clip.get('quality', 'unknown')
                quality_desc = QUALITY_PRESETS.get(quality, {}).get('desc', quality)
                await callback.message.answer_video(
                    f,
                    caption=f"🎬 {clip['name']}\n📊 Качество: {quality_desc}"
                )
        else:
            await callback.message.answer("❌ Файл не найден")
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('view_skinpack_'))
async def view_skinpack_callback(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    index = int(callback.data.split('_')[2])
    
    skinpacks = user_data.get
