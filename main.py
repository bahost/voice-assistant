import os
import tempfile
import speech_recognition as sr
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import logging
from pydub import AudioSegment

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# logger = logging.getLogger(name)

# Токен бота из BotFather
TOKEN = os.getenv("TG_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет сообщение при команде /start."""
    await update.message.reply_text(
        "Привет! Я бот для распознавания речи. Отправь мне голосовое сообщение, и я переведу его в текст."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет сообщение при команде /help."""
    await update.message.reply_text(
        "Просто отправь мне голосовое сообщение, и я преобразую его в текст."
    )

async def voice_to_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает голосовые сообщения и конвертирует их в текст."""
    # Сообщение о начале обработки
    processing_msg = await update.message.reply_text("Обрабатываю ваше голосовое сообщение...")
    
    try:
        # Получаем информацию о голосовом сообщении
        voice = update.message.voice
        
        # Получаем файл
        voice_file = await context.bot.get_file(voice.file_id)
        
        # Создаем временный файл для сохранения аудио
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as temp_ogg:
            ogg_path = temp_ogg.name
        
        # Скачиваем голосовое сообщение во временный файл
        await voice_file.download_to_drive(ogg_path)
        
        # Конвертируем OGG в WAV (speech_recognition работает с WAV)
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_wav:
            wav_path = temp_wav.name
        
        # Используем pydub для конвертации
        audio = AudioSegment.from_file(ogg_path, format="ogg")
        audio.export(wav_path, format="wav")
        
        # Инициализируем распознаватель речи
        recognizer = sr.Recognizer()
        
        # Открываем аудиофайл
        with sr.AudioFile(wav_path) as source:
            # Чтение аудиоданных из файла
            audio_data = recognizer.record(source)
            
            # Пытаемся распознать речь
            text = recognizer.recognize_google(audio_data, language="ru-RU")
            
            # Отправляем результат пользователю
            await update.message.reply_text(f"Распознанный текст: {text}")
    
    except sr.UnknownValueError:
        await update.message.reply_text("Извините, не удалось распознать речь.")
    except sr.RequestError as e:
        await update.message.reply_text(f"Ошибка сервиса распознавания: {e}")
    except Exception as e:
        # logger.error(f"Ошибка при обработке голосового сообщения: {e}")
        await update.message.reply_text("Произошла ошибка при обработке голосового сообщения.")
    finally:
        # Удаляем сообщение о процессе обработки
        await processing_msg.delete()
        
        # Удаляем временные файлы
        try:
            os.remove(ogg_path)
            os.remove(wav_path)
        except:
            pass

def main() -> None:
    """Запускает бота."""
    # Создаем приложение и передаем ему токен бота
    application = Application.builder().token(TOKEN).build()

    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # Обработчик голосовых сообщений
    application.add_handler(MessageHandler(filters.VOICE,voice_to_text))

    # Запускаем бота
    application.run_polling()

if __name__ == '__main__':
    main()
