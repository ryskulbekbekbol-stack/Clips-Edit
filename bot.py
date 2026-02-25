#!/usr/bin/env python3
import os
import sys
import subprocess
import tempfile
import shutil
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
import yt_dlp

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    print("❌ Токен не найден!")
    sys.exit(1)

TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

user_videos = {}
user_audios = {}

# ========== ТРИ МЕТОДА СКАЧИВАНИЯ ==========
def download_method1(url, temp_dir):
    """Метод 1: Android клиент"""
    output = os.path.join(temp_dir, 'video.%(ext)s')
    ydl_opts = {
        'format': 'best[height<=720]',
        'outtmpl': output,
        'quiet': True,
        'extractor_args': {'youtube': {'player_client': ['android']}}
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            base = filename.rsplit('.', 1)[0]
            if os.path.exists(base + '.mp4'):
                return base + '.mp4', info.get('title', 'video')
    except:
        pass
    return None, None

def download_method2(url, temp_dir):
    """Метод 2: Web клиент"""
    output = os.path.join(temp_dir, 'video.%(ext)s')
    ydl_opts = {
        'format': 'best[height<=720]',
        'outtmpl': output,
        'quiet': True,
        'extractor_args': {'youtube': {'player_client': ['web']}}
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            base = filename.rsplit('.', 1)[0]
            if os.path.exists(base + '.mp4'):
                return base + '.mp4', info.get('title', 'video')
    except:
        pass
    return None, None

def download_method3(url, temp_dir):
    """Метод 3: Минимальное качество"""
    output = os.path.join(temp_dir, 'video.mp4')
    ydl_opts = {
        'format': 'worst[ext=mp4]',
        'outtmpl': output,
        'quiet': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if os.path.exists(output):
                return output, info.get('title', 'video')
    except:
        pass
    return None, None

def download_video(url):
    """Пробует все три метода по очереди"""
    temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
    
    # Метод 1
    video_path, title = download_method1(url, temp_dir)
    if video_path:
        print("✅ Метод 1 сработал")
        return video_path, title, temp_dir
    
    # Метод 2
    video_path, title = download_method2(url, temp_dir)
    if video_path:
        print("✅ Метод 2 сработал")
        return video_path, title, temp_dir
    
    # Метод 3
    video_path, title = download_method3(url, temp_dir)
    if video_path:
        print("✅ Метод 3 сработал")
        return video_path, title, temp_dir
    
    shutil.rmtree(temp_dir)
    return None, None, None

def get_duration(file_path):
    """Длительность видео/аудио"""
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
           '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except:
        return 0

def create_beats(duration):
    """Создает биты (просто равномерно)"""
    beats = []
    interval = 0.5
    current = 0
    while current < duration:
        beats.append(current)
        current += interval
    return beats

def cut_video(video_path, beats, output_dir, clip_duration):
    """Режет видео"""
    clips = []
    video_duration = get_duration(video_path)
    
    # Ограничиваем биты длительностью видео
    valid_beats = [b for b in beats if b < video_duration]
    valid_beats = valid_beats[:min(len(valid_beats), 30)]
    
    for i in range(len(valid_beats)-1):
        start = valid_beats[i]
        end = valid_beats[i+1]
        
        if end - start < 0.3:
            continue
            
        output = os.path.join(output_dir, f"clip_{i:03d}.mp4")
        cmd = [
            'ffmpeg', '-i', video_path,
            '-ss', str(start),
            '-to', str(end),
            '-c', 'copy',
            '-an',
            '-y',
            output
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            clips.append(output)
        except:
            pass
    
    return clips

def merge_clips(clips, audio_path, output_path, clip_duration):
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
        
        trimmed = os.path.join(os.path.dirname(output_path), 'trimmed.mp3')
        trim_cmd = [
            'ffmpeg', '-i', audio_path,
            '-t', str(clip_duration),
            '-c', 'copy',
            '-y',
            trimmed
        ]
        subprocess.run(trim_cmd, check=True, capture_output=True)
        
        final_cmd = [
            'ffmpeg', '-i', merged,
            '-i', trimmed,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-map', '0:v:0',
            '-map', '1:a:0',
            '-shortest',
            '-y',
            output_path
        ]
        subprocess.run(final_cmd, check=True, capture_output=True)
        
        os.remove(merged)
        os.remove(trimmed)
        os.remove(list_file)
        return output_path
        
    except Exception as e:
        print(f"Ошибка склейки: {e}")
        return None

def compress_video(input_path):
    """Сжимает видео если надо"""
    size = os.path.getsize(input_path) / 1024 / 1024
    if size <= 45:
        return input_path
    
    output = input_path.replace('.mp4', '_small.mp4')
    cmd = [
        'ffmpeg', '-i', input_path,
        '-c:v', 'libx264',
        '-b:v', '1M',
        '-preset', 'fast',
        '-c:a', 'aac',
        '-b:a', '128k',
        '-y',
        output
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return output
    except:
        return input_path

# ========== КОМАНДЫ ==========
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.reply(
        "🎬 **Бот для нарезки**\n\n"
        "/yt <ссылка> <секунд> - скачать видео\n"
        "Потом отправь аудио"
    )

@dp.message_handler(commands=['yt'])
async def yt_command(message: types.Message):
    args = message.text.split()
    if len(args) < 3:
        await message.reply("❌ Формат: /yt ссылка секунд")
        return
    
    url = args[1]
    try:
        clip_duration = int(args[2])
        if clip_duration > 60:
            await message.reply("❌ Максимум 60 секунд")
            return
    except:
        await message.reply("❌ Секунды должны быть числом")
        return
    
    user_id = str(message.from_user.id)
    msg = await message.reply("⏬ Качаю видео...")
    
    video_path, title, temp_dir = download_video(url)
    
    if not video_path:
        await msg.edit_text("❌ Не удалось скачать")
        return
    
    await message.reply(f"✅ Видео скачано")
    
    user_videos[user_id] = {
        'path': video_path,
        'temp_dir': temp_dir,
        'duration': clip_duration
    }
    
    if user_id in user_audios:
        await msg.edit_text("✅ Есть видео и аудио, обрабатываю...")
        await process_files(message, user_id)
    else:
        await msg.edit_text("✅ Видео скачано! Теперь отправь аудио")

@dp.message_handler(content_types=['audio'])
async def handle_audio(message: types.Message):
    user_id = str(message.from_user.id)
    msg = await message.reply("⏬ Качаю аудио...")
    
    file = await bot.get_file(message.audio.file_id)
    temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
    audio_path = os.path.join(temp_dir, 'audio.mp3')
    await bot.download_file(file.file_path, audio_path)
    
    user_audios[user_id] = {
        'path': audio_path,
        'temp_dir': temp_dir
    }
    
    if user_id in user_videos:
        await msg.edit_text("✅ Есть видео и аудио, обрабатываю...")
        await process_files(message, user_id)
    else:
        await msg.edit_text("✅ Аудио скачано! Теперь отправь /yt")

async def process_files(message: types.Message, user_id: str):
    video_info = user_videos[user_id]
    audio_info = user_audios[user_id]
    clip_duration = video_info['duration']
    
    msg = await message.reply("🎵 Создаю биты...")
    
    beats = create_beats(clip_duration)
    
    if len(beats) < 2:
        await msg.edit_text("⚠️ Беру простую нарезку")
        beats = [0, clip_duration]
    
    await msg.edit_text(f"✂️ Режу видео...")
    
    work_dir = tempfile.mkdtemp(dir=TEMP_DIR)
    clips = cut_video(video_info['path'], beats, work_dir, clip_duration)
    
    if not clips:
        await msg.edit_text("❌ Не удалось нарезать")
        return
    
    await msg.edit_text(f"🔄 Склеиваю {len(clips)} кусков...")
    
    output_path = os.path.join(work_dir, 'final.mp4')
    result = merge_clips(clips, audio_info['path'], output_path, clip_duration)
    
    if not result:
        await msg.edit_text("❌ Не удалось склеить")
        return
    
    # Сжимаем если надо
    result = compress_video(result)
    size = os.path.getsize(result) / 1024 / 1024
    
    await msg.edit_text("✅ Готово! Отправляю...")
    
    with open(result, 'rb') as f:
        await message.reply_video(
            f,
            caption=f"🎬 Готово!\n⏱️ {clip_duration} сек\n✂️ {len(clips)} фрагментов\n💾 {size:.1f} MB"
        )
    
    # Чистим
    shutil.rmtree(work_dir)
    shutil.rmtree(video_info['temp_dir'])
    shutil.rmtree(audio_info['temp_dir'])
    del user_videos[user_id]
    del user_audios[user_id]

if __name__ == '__main__':
    print("🤖 Бот запущен (3 метода)")
    executor.start_polling(dp, skip_updates=True)
