import os
import logging
import requests
import json
import tempfile
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from gtts import gTTS
import uuid

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
        "Я буду отправлять как текстовые, так и голосовые сообщения. Просто напишите что-нибудь!"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    await update.message.reply_text(
        "Просто отправьте мне текстовое сообщение, и я отвечу вам текстом и голосовым сообщением."
    )

def text_to_speech(text, lang='ru'):
    """Преобразует текст в речь и сохраняет в аудиофайл"""
    # Создаем уникальное имя файла
    filename = os.path.join(TEMP_DIR, f"audio_{uuid.uuid4()}.mp3")
    
    # Генерируем аудио из текста
    tts = gTTS(text=text, lang=lang, slow=False)
    tts.save(filename)
    
    return filename

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик текстовых сообщений"""
    user_message = update.message.text
    
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
            audio_file =text_to_speech(bot_response)
            
            # Отправка голосового сообщения
            await update.message.reply_voice(
                voice=open(audio_file, 'rb'),
                caption="Голосовой ответ"
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

def main() -> None:
    """Запуск бота"""
    # Создание приложения
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Добавление обработчиков команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    # Добавление обработчика текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запуск бота
    application.run_polling()

if __name__ == "__main__":
    main()
