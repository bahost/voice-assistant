import os
import logging
import tempfile
import numpy as np
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)
from gtts import gTTS
import librosa
import soundfile as sf
import pyrubberband as pyrb

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger('logger')

# Состояния для ConversationHandler
VOICE, TEXT = range(2)

# Словарь для хранения голосовых образцов пользователей
user_voice_samples = {}
user_voice_features = {}  # Для хранения характеристик голоса

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало разговора и запрос голосового сообщения."""
    await update.message.reply_text(
        "Привет! Я бот, который попытается озвучить ваш текст в стиле вашего голоса.\n"
        "Сначала отправьте мне голосовое сообщение, чтобы я мог проанализировать характеристики вашего голоса."
    )
    return VOICE

async def voice_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка голосового сообщения."""
    user_id = update.effective_user.id
    
    # Создаем временный файл для голосового сообщения
    voice_file = await update.message.voice.get_file()
    
    voice_sample_file = tempfile.NamedTemporaryFile(delete=False, suffix='.ogg')
    voice_sample_path = voice_sample_file.name
    voice_sample_file.close()
    
    # Скачиваем голосовое сообщение
    await voice_file.download_to_drive(voice_sample_path)
    
    # Конвертируем в WAV для анализа
    wav_path = voice_sample_path.replace('.ogg', '.wav')
    os.system(f'ffmpeg -i {voice_sample_path} {wav_path} -y')
    
    try:
        # Анализируем характеристики голоса
        y, sr = librosa.load(wav_path, sr=None)
        
        # Извлекаем тональные характеристики
        # Используем f0 (основная частота) для определения высоты голоса
        f0, voiced_flag, voiced_probs = librosa.pyin(
            y, 
            fmin=librosa.note_to_hz('C2'), 
            fmax=librosa.note_to_hz('C7'),
            sr=sr
        )
        # Отфильтровываем NaN значения и усредняем
        f0_clean = f0[~np.isnan(f0)]
        if len(f0_clean) > 0:
            mean_f0 = np.mean(f0_clean)
        else:
            mean_f0 = 100  # Значение по умолчанию, если не удалось определить высоту голоса
        
        # Определяем темп
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        tempo, _ = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
        
        # Сохраняем характеристики для пользователя
        user_voice_features[user_id] = {
            'mean_f0': mean_f0,
            'tempo': tempo
        }
        
        # Сохраняем путь к образцу голоса
        user_voice_samples[user_id] = wav_path
        
        logger.info(f"Voice analysis for user {user_id}: f0={mean_f0}, tempo={tempo}")
        
        await update.message.reply_text(
            "Отлично! Я проанализировал ваш голос. "
            "Теперь отправьте текст, который вы хотите озвучить."
        )
        return TEXT
    except Exception as e:
        logger.error(f"Ошибка при анализе голоса: {e}")
        await update.message.reply_text(
            "Произошла ошибка при анализе вашего голоса. Пожалуйста, попробуйте снова или отправьте другой образец."
        )
        return VOICE

async def text_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка текста и генерация озвученного сообщения."""
    user_id = update.effective_user.id
    text = update.message.text
    
    #Проверяем, есть ли данные о голосе пользователя
    if user_id not in user_voice_features:
        await update.message.reply_text(
            "Я не нашел данных о вашем голосе. Пожалуйста, начните сначала с команды /start."
        )
        return ConversationHandler.END
    
    await update.message.reply_text("Генерирую голосовое сообщение, пожалуйста, подождите...")
    
    try:
        # Создаем временные файлы
        tts_output = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
        tts_output_path = tts_output.name
        tts_output.close()
        
        modified_output = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
        modified_output_path = modified_output.name
        modified_output.close()
        
        final_output = tempfile.NamedTemporaryFile(delete=False, suffix='.ogg')
        final_output_path = final_output.name
        final_output.close()
        
        # Генерируем базовую речь с помощью Google TTS
        tts = gTTS(text=text, lang='ru', slow=False)
        tts.save(tts_output_path)
        
        # Конвертируем mp3 в wav для обработки
        temp_wav = tts_output_path.replace('.mp3', '_temp.wav')
        os.system(f'ffmpeg -i {tts_output_path} {temp_wav} -y')
        
        # Загружаем аудио и модифицируем его в соответствии с характеристиками голоса пользователя
        y, sr = librosa.load(temp_wav, sr=None)
        
        # Получаем характеристики голоса пользователя
        voice_features = user_voice_features[user_id]
        
        # Анализируем текущий синтезированный голос
        f0, voiced_flag, voiced_probs = librosa.pyin(
            y, 
            fmin=librosa.note_to_hz('C2'), 
            fmax=librosa.note_to_hz('C7'),
            sr=sr
        )
        f0_clean = f0[~np.isnan(f0)]
        if len(f0_clean) > 0:
            tts_mean_f0 = np.mean(f0_clean)
        else:
            tts_mean_f0 = 200  # Стандартное значение для синтезированной речи
        
        # Вычисляем разницу в высоте тона между образцом и синтезом
        # Конвертируем в полутоны (semitones) для pyrubberband
        pitch_diff = 12 * np.log2(voice_features['mean_f0'] / tts_mean_f0)
        
        logger.info(f"Pitch difference: {pitch_diff} semitones (user: {voice_features['mean_f0']}, tts: {tts_mean_f0})")
        
        # Используем pyrubberband для изменения высоты тона
        y_shifted = pyrb.pitch_shift(y, sr, pitch_diff)
        
        # Можем также изменить темп, если нужно
        # tempo_ratio = voice_features['tempo'] / 120.0  # 120 BPM считаем "стандартным" темпом
        # y_modified = pyrb.time_stretch(y_shifted, sr, tempo_ratio)
        
        # Для простоты используем только изменение высоты тона
        y_modified = y_shifted
        
        # Сохраняем модифицированное аудио
        sf.write(modified_output_path, y_modified, sr)
        
        # Конвертируем в формат ogg для Telegram
        os.system(f'ffmpeg -i {modified_output_path} -c:a libopus {final_output_path} -y')
        
        # Отправляем аудио пользователю
        await update.message.reply_voice(voice=open(final_output_path, 'rb'))
        
        # Очищаем временные файлы
        for path in [tts_output_path, temp_wav, modified_output_path, final_output_path]:
            try:
                os.unlink(path)
            except:
                pass
        
        await update.message.reply_text(
            "Готово! Отправьте еще текст, чтобы озвучить его, или /start чтобы начать заново с другим голосом."
        )
        return TEXT
        
    except Exception as e:
        logger.error(f"Ошибка при генерации речи: {e}")
        await update.message.reply_text(
            "Произошла ошибка при генерации голосового сообщения. Пожалуйста, попробуйте снова."
        )
        return TEXT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена и завершение разговора."""
    user_id = update.effective_user.id
    
    # Удаляем данные пользователя
    if user_id in user_voice_samples:
        try:
            os.unlink(user_voice_samples[user_id])
            del user_voice_samples[user_id]
        except:
            pass
    
    if user_id in user_voice_features:
        del user_voice_features[user_id]
    
    await update.message.reply_text("Операция отменена. До свидания!")
    return ConversationHandler.END

def main() -> None:
    """Запуск бота."""
    # Создаем приложение и добавляем обработчики
    TG_TOKEN = os.getenv("TG_TOKEN")
    application = Application.builder().token(TG_TOKEN).build()
    
    # Настраиваем разговорный обработчик с состояниями
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            VOICE: [MessageHandler(filters.VOICE, voice_received)],
            TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, text_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    application.add_handler(conv_handler)
    
    # Запускаем бота
    application.run_polling()

if __name__ == "__main__":
    main()
