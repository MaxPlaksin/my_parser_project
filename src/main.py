import telebot
import pandas as pd
import re
import os
import logging
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("bot_log.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = '7136103155:AAHS8y4z7CsdSpddDddU6p60TM8dTFElXmY'
EXCEL_FILE = 'Остатки (1).xlsx'
SHEET_NAME = 'TDSheet'

# === ИНИЦИАЛИЗАЦИЯ БОТА ===
bot = telebot.TeleBot(TELEGRAM_TOKEN)


# === ЗАГРУЗКА EXCEL-БАЗЫ ===
def load_database():
    try:
        logger.info(f"📂 Загружаю Excel-файл {EXCEL_FILE}...")
        if not os.path.exists(EXCEL_FILE):
            logger.error(f"Файл {EXCEL_FILE} не найден!")
            return None

        df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_NAME)
        df = df.dropna(subset=['Номенклатура', 'Артикул'])

        # Преобразуем только строковые колонки в строки
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str)

        # Добавляем нормализованные артикулы сразу при загрузке
        df['Артикул_clean'] = df['Артикул'].apply(normalize)

        logger.info(f"✅ База загружена успешно: {len(df)} записей")
        return df
    except Exception as e:
        logger.error(f"Ошибка при загрузке базы: {e}")
        return None


# === НОРМАЛИЗАЦИЯ ===
def normalize(text):
    if pd.isna(text):
        return ''
    text = str(text).strip()
    text = text.replace('\xa0', '').replace('\u202f', '')  # неразрывные пробелы
    text = re.sub(r'[\s\-\/]', '', text)  # убираем пробелы, слэши, тире
    if text.endswith('.0'):
        text = text[:-2]
    return text.lower()


# === ПОИСК ПО БАЗЕ ===
def find_best_matches(user_input, df):
    if df is None:
        return "⚠️ База данных не загружена. Обратитесь к администратору."

    try:
        # 1. Извлекаем всё, что похоже на артикул: буквы/цифры/тире/слэш, от 4 символов
        raw_candidates = re.findall(r'[\w\-\/]{4,}', user_input)
        cleaned_inputs = list(set([normalize(x) for x in raw_candidates if x.strip()]))

        if not cleaned_inputs:
            return "⛔️ В сообщении не найден ни один артикул. Пожалуйста, укажите артикул товара."

        # 2. Ищем совпадения
        found_rows = df[df['Артикул_clean'].isin(cleaned_inputs)]

        if found_rows.empty:
            return f"❌ Ни один артикул не найден в базе. Проверьте правильность ввода."

        # 3. Убираем дубликаты
        unique_rows = found_rows.drop_duplicates(subset='Артикул_clean', keep='first')

        # 4. Собираем результат
        results = []
        for _, row in unique_rows.iterrows():
            price = str(row.get('Цена', '')).strip()
            currency = str(row.get('Валюта', '')).strip()

            # Проверка на NaN и пустые значения
            price_text = "нет" if price.lower() == 'nan' or not price.strip() else f"{price} {currency}".strip()

            # Безопасное получение значений с проверкой на NaN
            def safe_get(row, col, default='—'):
                val = row.get(col, default)
                return default if str(val).lower() == 'nan' else val

            results.append(
                f"📦 Артикул: {row['Артикул']}\n"
                f"Наименование: {safe_get(row, 'Номенклатура')}\n"
                f"Код: {safe_get(row, 'Номенклатура.Код')}\n"
                f"Склад: {safe_get(row, 'Склад')}\n"
                f"Остаток: {safe_get(row, 'Остаток')}\n"
                f"Цена: {price_text}\n"
            )

        # Ограничиваем количество результатов
        result_text = "\n".join(results[:20])
        if len(results) > 20:
            result_text += f"\n...и ещё {len(results) - 20} позиций"

        return result_text
    except Exception as e:
        logger.error(f"Ошибка при поиске: {e}")
        return f"⚠️ Произошла ошибка при поиске. Попробуйте позже."


# === ОБРАБОТКА КОМАНД ===
@bot.message_handler(commands=['start', 'help'])
def handle_start_help(message):
    help_text = (
        "🔍 *Бот для поиска товаров по артикулу*\n\n"
        "Отправьте мне артикул товара, и я найду информацию о нём в базе.\n"
        "Артикул должен содержать не менее 4 символов.\n\n"
        "Примеры запросов:\n"
        "• `ABC1234`\n"
        "• `Нужна информация по XYZ-5678`\n"
        "• `Проверь наличие товаров: ABC1234, DEF5678`\n\n"
        "Бот игнорирует регистр и разделители в артикулах."
    )
    bot.send_message(message.chat.id, help_text, parse_mode='Markdown')


@bot.message_handler(commands=['reload'])
def handle_reload(message):
    bot.send_message(message.chat.id, "🔄 Перезагружаю базу данных...")
    global df
    df = load_database()
    if df is not None:
        bot.send_message(message.chat.id, f"✅ База успешно перезагружена. Записей: {len(df)}")
    else:
        bot.send_message(message.chat.id, "❌ Не удалось загрузить базу данных.")


# === ОБРАБОТКА СООБЩЕНИЙ ОТ ПОЛЬЗОВАТЕЛЕЙ ===
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        user_text = message.text
        logger.info(f"Получен запрос от {message.from_user.id}: {user_text}")

        bot.send_chat_action(message.chat.id, 'typing')
        reply = find_best_matches(user_text, df)

        # Разбиваем длинные сообщения
        if len(reply) > 4000:
            parts = [reply[i:i + 4000] for i in range(0, len(reply), 4000)]
            for part in parts:
                bot.send_message(message.chat.id, part)
        else:
            bot.reply_to(message, reply)

        logger.info(f"Отправлен ответ пользователю {message.from_user.id}")
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}")
        bot.send_message(message.chat.id, "⚠️ Произошла ошибка при обработке запроса. Попробуйте позже.")


# === ЗАПУСК ===
if __name__ == "__main__":
    # Загружаем базу при запуске
    df = load_database()

    if df is None:
        print("⚠️ Не удалось загрузить базу данных. Бот будет запущен, но поиск будет недоступен.")

    print("✅ Бот запущен и ждёт запросы...")

    # Запускаем бота с обработкой ошибок
    try:
        bot.polling(non_stop=True, timeout=60, long_polling_timeout=30)
    except Exception as e:
        logger.critical(f"Критическая ошибка при работе бота: {e}")
