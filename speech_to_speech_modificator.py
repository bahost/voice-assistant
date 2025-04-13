import os
import tempfile
from pathlib import Path
import numpy as np
import torch
import torchaudio
import torchaudio.transforms as T
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# Настройка API токена Telegram бота
TELEGRAM_TOKEN = os.getenv("TG_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет сообщение при команде /start."""
    await update.message.reply_text('Привет! Отправь мне голосовое сообщение, и я изменю голос.')

async def process_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает голосовые сообщения."""
    # Уведомление о начале обработки
    await update.message.reply_text("Обрабатываю ваше голосовое сообщение...")
    
    # Создаем временные файлы для обработки
    with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as voice_file, \
         tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as wav_file, \
         tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as output_wav_file, \
         tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as output_voice_file:
        
        voice_file_path = voice_file.name
        wav_file_path = wav_file.name
        output_wav_path = output_wav_file.name
        output_voice_path = output_voice_file.name
    
    # Скачиваем голосовое сообщение
    voice_message = await update.message.voice.get_file()
    await voice_message.download_to_drive(voice_file_path)
    
    # Конвертируем .ogg в .wav для обработки
    os.system(f"ffmpeg -i {voice_file_path} {wav_file_path} -y")
    
    # Загружаем аудиофайл с помощью torchaudio
    waveform, sample_rate = torchaudio.load(wav_file_path)
    
    # Изменяем голос (в этом примере используем изменение высоты)
    effects = [
        ["pitch", "100"],  # Изменение высоты голоса
        ["rate", "44100"],  # Установка частоты дискретизации
    ]
    
    # Применяем эффекты
    transformed_waveform, transformed_sample_rate = torchaudio.sox_effects.apply_effects_tensor(
        waveform, sample_rate, effects
    )
    
    # Сохраняем преобразованный файл
    torchaudio.save(output_wav_path, transformed_waveform, transformed_sample_rate)
    
    # Конвертируем обратно в формат .ogg для отправки в Telegram
    os.system(f"ffmpeg -i {output_wav_path} -c:a libopus {output_voice_path} -y")
    
    # Отправляем обработанное голосовое сообщение обратно
    await update.message.reply_voice(voice=open(output_voice_path, 'rb'))
    
    # Удаляем временные файлы
    for file_path in [voice_file_path, wav_file_path, output_wav_path, output_voice_path]:
        try:
            os.unlink(file_path)
        except:
            pass

def main() -> None:
    """Запускает бота."""
    # Создаем приложение и добавляем обработчики
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.VOICE, process_voice))
    
    # Запускаем бота
    application.run_polling()

if __name__ == "__main__":
    main()
