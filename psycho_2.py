import os
import logging
import requests
import json
import tempfile
import uuid
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from gtts import gTTS
import speech_recognition as sr
from pydub import AudioSegment
import io

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger('name')

# Конфигурация
TELEGRAM_TOKEN = os.getenv("TG_TOKEN")  # Замените на ваш токен Telegram бота
YANDEX_API_KEY = os.getenv("YAGPT_TOKEN")  # Замените на ваш ключ API YandexGPT
YANDEX_FOLDER_ID = os.getenv("FOLDER_ID")  # Замените на ваш folder_id из Yandex Cloud

# Предварительный промпт для модели
SYSTEM_PROMPT = """
Ты профессиональный психолог на сеансе психотерапии. Помоги мне разобраться в моих чувствах, иногда задавай мне уточняющий вопрос. Отвечай сообщением короче 4 предложений.
"""  # Можете изменить на свой промпт

# URL для запросов к YandexGPT
YANDEX_GPT_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

# Создание временной директории для аудиофайлов
TEMP_DIR = tempfile.mkdtemp()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    await update.message.reply_text(
        "Привет! Я бот, который использует YandexGPT для ответов на ваши сообщения. "
        "Я могу принимать как текстовые, так и голосовые сообщения, "
        "и буду отвечать в обоих форматах. Просто напишите или наговорите что-нибудь!"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    await update.message.reply_text(
        "Я могу работать с текстовыми и голосовыми сообщениями:\n"
        "- Отправьте мне текст, и я отвечу текстом и голосовым сообщением\n"
        "- Отправьте мне голосовое сообщение, я распознаю его и также отвечу в обоих форматах"
    )

def text_to_speech(text, lang='ru'):
    """Преобразует текст в речь и сохраняет в аудиофайл"""
    # Создаем уникальное имя файла
    filename = os.path.join(TEMP_DIR, f"audio_{uuid.uuid4()}.mp3")
    
    # Генерируем аудио из текста
    tts = gTTS(text=text, lang=lang, slow=False)
    tts.save(filename)
    
    return filename

async def process_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает голосовые сообщения"""
    # Получение информации о файле
    voice_file = await update.message.voice.get_file()
    
    # Скачивание голосового сообщения
    voice_ogg = os.path.join(TEMP_DIR, f"voice_{uuid.uuid4()}.ogg")
    await voice_file.download_to_drive(voice_ogg)
    
    # Конвертирование из .ogg в .wav (для распознавания)
    voice_wav = os.path.join(TEMP_DIR, f"voice_{uuid.uuid4()}.wav")
    audio = AudioSegment.from_file(voice_ogg, format="ogg")
    audio.export(voice_wav, format="wav")
    
    # Распознавание речи
    r = sr.Recognizer()
    with sr.AudioFile(voice_wav) as source:
        audio_data = r.record(source)
        try:
            # Определяем язык автоматически или можно задать конкретный язык
            user_message = r.recognize_google(audio_data, language="ru-RU")
            # Сообщаем пользователю, что мы распознали
            await update.message.reply_text(f"Я распознал: {user_message}")
            # Обрабатываем распознанный текст
            await process_text_query(update, user_message)
        except sr.UnknownValueError:
            await update.message.reply_text("Извините, я не смог распознать ваше сообщение.")
        except sr.RequestError as e:
            await update.message.reply_text(f"Ошибка при распознавании речи: {str(e)}")
    
    # Удаление временных файлов
    try:
        os.remove(voice_ogg)
        os.remove(voice_wav)
    except Exception as e:
        logger.error(f"Ошибка при удалении временных файлов: {e}")

async def process_text_query(update: Update, user_message):
    """Обрабатывает текстовый запрос и генерирует ответ от YandexGPT"""
    # Отправка печатающего статуса
    await update.message.chat.send_action(action="typing")
    
    try:
        # Формирование заголовков для запроса
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {YANDEX_API_KEY}",
            "x-folder-id": YANDEX_FOLDER_ID
        }
        
        # Формирование тела запроса
        payload = {
            "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",  # Можно изменить на другую модель YandexGPT
            "completionOptions": {
                "stream": False,
                "temperature": 0.6,
                "maxTokens": 1000
            },
            "messages": [
                {
                    "role": "system",
                    "text": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "text": user_message
                }
            ]
        }
        
        # Отправка запроса к YandexGPT
        response = requests.post(YANDEX_GPT_URL, headers=headers, json=payload)
        
        # Проверка успешности запроса
        if response.status_code == 200:
            # Парсинг ответа
            response_json = response.json()
            bot_response = response_json["result"]["alternatives"][0]["message"]["text"]
            
            # Отправка текстового ответа пользователю
            await update.message.reply_text(bot_response)
            
            # Озвучивание ответа
            await update.message.chat.send_action(action="record_voice")
            audio_file = text_to_speech(bot_response)
            
            # Отправка голосового сообщения
            await update.message.reply_voice(
                voice=open(audio_file, 'rb')
            )
            
            # Удаление временного файла
            try:
                os.remove(audio_file)
            except Exception as e:
                logger.error(f"Ошибка при удалении аудиофайла: {e}")
            
        else:
            logger.error(f"Ошибка API YandexGPT: {response.status_code}, {response.text}")
            await update.message.reply_text(
                "Извините, произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже."
            )
        
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}")
        await update.message.reply_text(
            "Извините, произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже."
        )

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик текстовых сообщений"""
    user_message = update.message.text
    await process_text_query(update, user_message)

def main() -> None:
    """Запуск бота"""
    # Создание приложения
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Добавление обработчиков команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    # Обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    # Обработчик голосовых сообщений
    application.add_handler(MessageHandler(filters.VOICE, process_voice_message))

    # Запуск бота
    application.run_polling()

if __name__ == "__main__":
    main()
