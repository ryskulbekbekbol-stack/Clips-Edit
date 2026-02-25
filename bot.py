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
    print("❌ СУКА, ТОКЕН НЕ УСТАНОВЛЕН!")
    sys.exit(1)

TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

user_videos = {}
user_audios = {}

# ========== ХУЕВАЯ ФУНКЦИЯ СКАЧИВАНИЯ ==========
def download_video(url):
    """СПИЗДИТ ВИДЕО С YOUTUBE ЛЮБЫМ СПОСОБОМ"""
    temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
    output = os.path.join(temp_dir, 'video.mp4')
    
    # ПИЗДАТЫЕ НАСТРОЙКИ
    ydl_opts = {
        'format': 'best[height<=720]',
        'outtmpl': output,
        'quiet': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android'],  # ЕБАШИМ АНДРОИД КЛИЕНТ
            }
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if os.path.exists(output):
                return output, info.get('title', 'хуй знает'), temp_dir
    except Exception as e:
        print(f"❌ ПИЗДЕЦ: {e}")
        shutil.rmtree(temp_dir)
        return None, None, None

# ========== ПРОСТЕЙШИЙ ОПРЕДЕЛИТЕЛЬ БИТОВ ==========
def create_beats(duration):
    """ЕБАШИТ БИТЫ ЧЕРЕЗ ЖОПУ"""
    beats = []
    interval = 0.5  # 120 BPM
    current = 0
    while current < duration:
        beats.append(current)
        current += interval
    return beats

# ========== ХУЕВАЯ ФУНКЦИЯ НАРЕЗКИ ==========
def cut_video(video_path, beats, output_dir, clip_duration):
    """РЕЖЕТ ВИДЕО НАХУЙ"""
    clips = []
    
    # Ограничиваем количество битов
    max_beats = min(len(beats), 30)
    beats = beats[:max_beats]
    
    for i in range(len(beats)-1):
        start = beats[i]
        end = beats[i+1]
        
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

# ========== ПИЗДАТАЯ ФУНКЦИЯ СКЛЕЙКИ ==========
def merge_video_audio(clips, audio_path, output_path, clip_duration):
    """СКЛЕИВАЕТ ВИДЕО И НАКЛАДЫВАЕТ АУДИО"""
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
        
        # Обрезаем аудио
        trimmed_audio = os.path.join(os.path.dirname(output_path), 'audio.mp3')
        trim_cmd = [
            'ffmpeg', '-i', audio_path,
            '-t', str(clip_duration),
            '-c', 'copy',
            '-y',
            trimmed_audio
        ]
        subprocess.run(trim_cmd, check=True, capture_output=True)
        
        # Склеиваем
        final_cmd = [
            'ffmpeg', '-i', merged,
            '-i', trimmed_audio,
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
        os.remove(trimmed_audio)
        os.remove(list_file)
        return output_path
        
    except:
        return None

# ========== КОМАНДЫ ==========
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.reply(
        "🎬 **ПИЗДАТЫЙ БОТ**\n\n"
        "1. /yt ССЫЛКА СЕКУНД\n"
        "2. ОТПРАВЬ АУДИО\n"
        "3. ПОЛУЧИ КЛИП\n\n"
        "Пример: /yt https://youtu.be/... 17"
    )

@dp.message_handler(commands=['yt'])
async def yt_command(message: types.Message):
    args = message.text.split()
    if len(args) < 3:
        await message.reply("❌ ЕБЛАН, ПИШИ: /yt ссылка секунд")
        return
    
    url = args[1]
    try:
        clip_duration = int(args[2])
        if clip_duration > 60:
            await message.reply("❌ НАХУЯ ТАК МНОГО? МАКСИМУМ 60 СЕКУНД")
            return
    except:
        await message.reply("❌ СЕКУНДЫ ДОЛЖНЫ БЫТЬ ЧИСЛОМ, ДОЛБОЁБ")
        return
    
    user_id = str(message.from_user.id)
    msg = await message.reply("⏬ КАЧАЮ ВИДЕО...")
    
    video_path, title, temp_dir = download_video(url)
    
    if not video_path:
        await msg.edit_text("❌ НЕ УДАЛОСЬ СКАЧАТЬ. ЮТУБ БЛОКИРУЕТ ПИДОРЫ")
        return
    
    # Получаем длительность
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    video_duration = float(result.stdout.strip())
    
    await message.reply(f"✅ ВИДЕО СКАЧАНО! {video_duration:.0f} СЕКУНД")
    
    user_videos[user_id] = {
        'path': video_path,
        'temp_dir': temp_dir,
        'duration': clip_duration
    }
    
    if user_id in user_audios:
        await msg.edit_text("✅ ЕСТЬ ВИДЕО И АУДИО, ОБРАБАТЫВАЮ...")
        await process_files(message, user_id)
    else:
        await msg.edit_text("✅ ВИДЕО СКАЧАНО! ТЕПЕРЬ КИДАЙ АУДИО")

@dp.message_handler(content_types=['audio'])
async def handle_audio(message: types.Message):
    user_id = str(message.from_user.id)
    msg = await message.reply("⏬ КАЧАЮ АУДИО...")
    
    file = await bot.get_file(message.audio.file_id)
    temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
    audio_path = os.path.join(temp_dir, 'audio.mp3')
    await bot.download_file(file.file_path, audio_path)
    
    user_audios[user_id] = {
        'path': audio_path,
        'temp_dir': temp_dir
    }
    
    if user_id in user_videos:
        await msg.edit_text("✅ ЕСТЬ ВИДЕО И АУДИО, ОБРАБАТЫВАЮ...")
        await process_files(message, user_id)
    else:
        await msg.edit_text("✅ АУДИО СКАЧАНО! ТЕПЕРЬ КИДАЙ /yt")

async def process_files(message: types.Message, user_id: str):
    video_info = user_videos[user_id]
    audio_info = user_audios[user_id]
    clip_duration = video_info['duration']
    
    msg = await message.reply("🎵 ЕБУ БИТЫ...")
    
    # Создаём биты
    beats = create_beats(clip_duration)
    
    if len(beats) < 2:
        await msg.edit_text("❌ НЕ ПОЛУЧИЛОСЬ, НО ХУЙ С НИМ")
        beats = [0, clip_duration]
    
    await msg.edit_text(f"✂️ РЕЖУ ВИДЕО НА {len(beats)-1} КУСКОВ...")
    
    work_dir = tempfile.mkdtemp(dir=TEMP_DIR)
    clips = cut_video(video_info['path'], beats, work_dir, clip_duration)
    
    if not clips:
        await msg.edit_text("❌ НЕ УДАЛОСЬ НАРЕЗАТЬ, ПИЗДЕЦ")
        return
    
    await msg.edit_text(f"🔄 СКЛЕИВАЮ {len(clips)} КУСКОВ...")
    
    output_path = os.path.join(work_dir, 'final.mp4')
    result = merge_video_audio(clips, audio_info['path'], output_path, clip_duration)
    
    if not result:
        await msg.edit_text("❌ НЕ УДАЛОСЬ СКЛЕИТЬ, ПИЗДЕЦ")
        return
    
    size = os.path.getsize(result) / 1024 / 1024
    
    await msg.edit_text("✅ ГОТОВО! ОТПРАВЛЯЮ...")
    
    with open(result, 'rb') as f:
        await message.reply_video(
            f,
            caption=f"🎬 **ГОТОВО!**\n🎵 {clip_duration} СЕКУНД\n✂️ {len(clips)} ФРАГМЕНТОВ\n💾 {size:.1f} МБ"
        )
    
    # ЧИСТИМ ХУЙНЮ
    shutil.rmtree(work_dir)
    shutil.rmtree(video_info['temp_dir'])
    shutil.rmtree(audio_info['temp_dir'])
    del user_videos[user_id]
    del user_audios[user_id]

if __name__ == '__main__':
    print("🤬 ПИЗДАТЫЙ БОТ ЗАПУЩЕН")
    executor.start_polling(dp, skip_updates=True)
