import telebot
import pandas as pd
import re
import os
import logging
from mail_watcher import run_scheduled_check

# === ЛОГГИРОВАНИЕ ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("bot_log.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = '7136103155:AAHS8y4z7CsdSpddDddU6p60TM8dTFElXmY'
HTML_FILE = 'для бота (HTML4).html'

bot = telebot.TeleBot(TELEGRAM_TOKEN)


def normalize(text):
    """Нормализация текста для простых числовых артикулов"""
    if pd.isna(text):
        return ''
    text = str(text).strip()
    text = text.replace('\xa0', '').replace('\u202f', '')
    # Для числовых артикулов оставляем только цифры
    text = re.sub(r'[^\d]', '', text)
    if text.endswith('.0'):
        text = text[:-2]
    return text.lower()


def normalize_with_spaces(text):
    """Нормализация текста с сохранением пробелов для составных артикулов"""
    if pd.isna(text):
        return ''
    text = str(text).strip()
    text = text.replace('\xa0', ' ').replace('\u202f', ' ')
    # Заменяем все нецифровые символы (кроме пробелов) на пробелы
    text = re.sub(r'[^\d\s]', ' ', text)
    # Заменяем множественные пробелы на один пробел
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text.lower()


def safe_get(row, col, default='—'):
    val = row.get(col, default)
    return default if str(val).lower() in ['nan', 'none', ''] else val


def load_database():
    try:
        logger.info(f"📂 Загружаю HTML-файл {HTML_FILE}...")
        if not os.path.exists(HTML_FILE):
            logger.error(f"Файл {HTML_FILE} не найден.")
            return None

        tables = pd.read_html(HTML_FILE)
        df_local = tables[0]

        df_local.columns = df_local.iloc[0].map(str).str.strip()
        df_local = df_local.iloc[1:].reset_index(drop=True)
        df_local = df_local.astype(str)

        # Создаем два столбца для поиска: один для простых артикулов, другой для составных
        df_local['Артикул_clean'] = df_local['Артикул'].apply(normalize)
        df_local['Артикул_with_spaces'] = df_local['Артикул'].apply(normalize_with_spaces)

        logger.info(f"✅ База успешно загружена. Записей: {len(df_local)}")
        return df_local
    except Exception as e:
        logger.error(f"Ошибка при загрузке базы: {e}")
        return None


def find_best_matches(user_input, df_data):
    if df_data is None:
        return "⚠️ База не загружена. Используйте /reload или обратитесь к администратору."

    try:
        # Предварительная обработка: разбиваем многострочный текст на строки
        # и обрабатываем каждую строку отдельно
        lines = user_input.split('\n')
        all_potential_compound_articles = []
        all_potential_simple_articles = []

        for line in lines:
            # 1. Ищем составные артикулы (группы цифр, разделенные пробелами)
            # Находим последовательности из 2-4 групп цифр, разделенных пробелами
            compound_pattern = r'\b\d{2,5}(?:\s+\d{1,5}){1,3}\b'
            potential_compound_articles = re.findall(compound_pattern, line)
            all_potential_compound_articles.extend(potential_compound_articles)

            # 2. Ищем простые числовые артикулы (последовательности цифр)
            simple_pattern = r'\b\d{4,}\b'
            potential_simple_articles = re.findall(simple_pattern, line)
            all_potential_simple_articles.extend(potential_simple_articles)

        logger.info(f"Найдены потенциальные составные артикулы: {all_potential_compound_articles}")

        # Нормализуем составные артикулы, сохраняя пробелы
        normalized_compound_candidates = [normalize_with_spaces(c) for c in all_potential_compound_articles]
        logger.info(f"Нормализованные составные артикулы: {normalized_compound_candidates}")

        # Исключаем части составных артикулов из простых
        for compound in all_potential_compound_articles:
            for part in re.findall(r'\d+', compound):
                if part in all_potential_simple_articles:
                    all_potential_simple_articles.remove(part)

        logger.info(f"Найдены простые числовые артикулы: {all_potential_simple_articles}")

        # Нормализуем простые артикулы
        normalized_simple_candidates = [normalize(c) for c in all_potential_simple_articles]
        logger.info(f"Нормализованные простые артикулы: {normalized_simple_candidates}")

        # Объединяем все кандидаты
        all_candidates = normalized_simple_candidates + normalized_compound_candidates

        if not all_candidates:
            return "⛔️ Не найден ни один артикул в сообщении."

        # Проверяем наличие артикулов в базе
        found_rows = pd.DataFrame()
        found_articles = []
        not_found_articles = []

        # Сначала ищем составные артикулы (строгое соответствие)
        for candidate in normalized_compound_candidates:
            # Строгий поиск по точному соответствию
            matches = df_data[df_data['Артикул_with_spaces'] == candidate]
            if not matches.empty:
                found_rows = pd.concat([found_rows, matches])
                found_articles.append(candidate)
            else:
                not_found_articles.append(candidate)

        # Затем ищем простые артикулы (строгое соответствие)
        for candidate in normalized_simple_candidates:
            # Строгий поиск по точному соответствию
            matches = df_data[df_data['Артикул_clean'] == candidate]
            if not matches.empty:
                found_rows = pd.concat([found_rows, matches])
                found_articles.append(candidate)
            else:
                not_found_articles.append(candidate)

        logger.info(f"Найдены в базе: {found_articles}")
        logger.info(f"Не найдены в базе: {not_found_articles}")

        if found_rows.empty:
            return "❌ Ни один артикул не найден в базе."

        unique_rows = found_rows.drop_duplicates(subset='Артикул', keep='first')

        results = []
        for _, row in unique_rows.iterrows():
            price = safe_get(row, 'Цена', '')
            currency = safe_get(row, 'Валюта', '')
            price_text = "нет" if price.lower() in ['nan', '', 'none'] else f"{price} {currency}".strip()

            results.append(
                f"📦 Артикул: {row['Артикул']}\n"
                f"Наименование: {safe_get(row, 'Номенклатура')}\n"
                f"Код: {safe_get(row, 'Номенклатура.Код')}\n"
                f"Склад: {safe_get(row, 'Склад')}\n"
                f"Остаток: {safe_get(row, 'Остаток')}\n"
                f"Цена: {price_text}\n"
            )

        reply = "\n".join(results[:20])
        if len(results) > 20:
            reply += f"\n...и ещё {len(results) - 20} позиций"

        # Добавляем информацию о ненайденных артикулах, если они есть
        if not_found_articles:
            reply += f"\n\n⚠️ Не найдены в базе: {', '.join(not_found_articles)}"

        return reply
    except Exception as e:
        logger.error(f"Ошибка при поиске: {e}")
        return "⚠️ Произошла ошибка при поиске. Попробуйте позже."


@bot.message_handler(commands=['start', 'help'])
def handle_start_help(message):
    help_text = (
        "🔍 *Бот для поиска товаров по артикулу (HTML-база)*\n\n"
        "Отправьте мне артикул товара — и я найду его в базе.\n"
        "Примеры:\n"
        "`805015`\n"
        "`где 805015 и 805017`\n"
        "`код 3546945`\n"
        "`3222 3390 07`\n"
        "`3128 0619 00`\n"
    )
    bot.send_message(message.chat.id, help_text, parse_mode='Markdown')


@bot.message_handler(commands=['reload'])
def handle_reload(message):
    global df
    bot.send_message(message.chat.id, "🔄 Перезагружаю HTML-базу...")
    df = load_database()
    if df is not None:
        bot.send_message(message.chat.id, f"✅ База загружена. Записей: {len(df)}")
    else:
        bot.send_message(message.chat.id, "❌ Не удалось загрузить HTML-базу.")


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        user_text = message.text
        logger.info(f"Запрос от {message.from_user.id}: {user_text}")
        bot.send_chat_action(message.chat.id, 'typing')
        reply = find_best_matches(user_text, df)

        for i in range(0, len(reply), 4000):
            bot.send_message(message.chat.id, reply[i:i + 4000])

    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}")
        bot.send_message(message.chat.id, "⚠️ Ошибка при обработке запроса.")


if __name__ == "__main__":
    run_scheduled_check()
    df = load_database()
    print("✅ HTML-бот запущен и ждёт запросы...")
    try:
        bot.polling(non_stop=True, timeout=60, long_polling_timeout=30)
    except Exception as e:
        logger.critical(f"Критическая ошибка бота: {e}")
