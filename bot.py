#!/usr/bin/env python3
import os
import sys
import subprocess
import tempfile
import shutil
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
import yt_dlp

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    print("❌ Ошибка: BOT_TOKEN не установлен!")
    sys.exit(1)

TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
# ================================

def get_video_info(url):
    """Получает информацию о видео без скачивания"""
    ydl_opts = {'quiet': True, 'no_warnings': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

def download_clip(url, start_time, duration):
    """
    Скачивает и нарезает клип из YouTube видео.
    Возвращает путь к файлу и название видео.
    """
    temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
    output_template = os.path.join(temp_dir, '%(title)s.%(ext)s')
    
    # Настройки для скачивания и нарезки за один проход
    ydl_opts = {
        'format': 'best[height<=720]',  # Ограничим качество для скорости
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        # Ключевая часть: нарезка через FFmpeg
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'postprocessor_args': [
            '-ss', str(start_time),          # Начало
            '-t', str(duration),              # Длительность
            '-c', 'copy'                       # Копируем без перекодирования (быстро)
        ],
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            # yt-dlp может изменить расширение
            base = os.path.splitext(filename)[0]
            for ext in ['.mp4', '.mkv', '.webm']:
                if os.path.exists(base + ext):
                    return base + ext, info.get('title', 'video'), temp_dir
    except Exception as e:
        print(f"Ошибка скачивания: {e}")
    
    shutil.rmtree(temp_dir)
    return None, None, None

def compress_video(input_path, max_size_mb=45):
    """Сжимает видео, если оно больше лимита Telegram (45 МБ)"""
    size = os.path.getsize(input_path) / (1024 * 1024)
    if size <= max_size_mb:
        return input_path
    
    output_path = input_path.replace('.mp4', '_compressed.mp4')
    cmd = [
        'ffmpeg', '-i', input_path,
        '-c:v', 'libx264',
        '-b:v', '1M',           # Целевой битрейт
        '-preset', 'fast',
        '-c:a', 'aac',
        '-b:a', '128k',
        '-y',
        output_path
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        if os.path.getsize(output_path) / (1024 * 1024) <= max_size_mb:
            return output_path
    except:
        pass
    return input_path

# ========== КОМАНДЫ БОТА ==========
@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    await message.reply(
        "🎬 **YouTube Clip Bot**\n\n"
        "Пришли мне команду в формате:\n"
        "`/yt <ссылка> <длительность в секундах>`\n\n"
        "Например: `/yt https://youtu.be/V0HagC8EAPc 17`\n\n"
        "Я скачаю видео и пришлю тебе клип заданной длины (начиная с начала видео).",
        parse_mode='Markdown'
    )

@dp.message_handler(commands=['yt'])
async def yt_command(message: types.Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.reply("❌ Нужно указать ссылку и длительность!\nПример: `/yt https://youtu.be/... 17`")
        return
    
    url = args[1]
    try:
        duration = int(args[2])
        if duration <= 0:
            raise ValueError
    except:
        await message.reply("❌ Длительность должна быть положительным числом (секунды).")
        return
    
    # Получаем информацию о видео
    status_msg = await message.reply("🔍 Получаю информацию о видео...")
    try:
        info = get_video_info(url)
        video_duration = info.get('duration', 0)
        if duration > video_duration:
            await status_msg.edit_text(f"❌ Видео всего {video_duration} сек. Укажи меньшую длительность.")
            return
    except Exception as e:
        await status_msg.edit_text(f"❌ Не удалось получить информацию о видео: {e}")
        return
    
    await status_msg.edit_text(f"⏬ Скачиваю и нарезаю клип на {duration} сек...")
    
    # Скачиваем и нарезаем
    video_path, title, temp_dir = download_clip(url, 0, duration)
    
    if not video_path:
        await status_msg.edit_text("❌ Не удалось скачать видео.")
        return
    
    # Проверяем размер и сжимаем если нужно
    file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
    if file_size_mb > 45:
        await status_msg.edit_text(f"📦 Видео {file_size_mb:.1f} МБ (больше 45 МБ). Сжимаю...")
        video_path = compress_video(video_path)
    
    # Отправляем результат
    with open(video_path, 'rb') as f:
        await message.reply_video(
            f,
            caption=f"🎬 Клип из видео: {title}\n⏱️ Длительность: {duration} сек"
        )
    
    # Удаляем временную папку
    shutil.rmtree(temp_dir)

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    print("🤖 YouTube Clip Bot запущен")
    executor.start_polling(dp, skip_updates=True)
