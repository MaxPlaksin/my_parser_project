import telebot
import pandas as pd
import re
import os
import logging
from mail_watcher import run_scheduled_check
import time
from threading import Thread

# === ЛОГГИРОВАНИЕ ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("bot_log.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = '7706134881:AAFuAnYhPM1LcDNK_ZAfhwTINCX6nK34-Co'
EXCEL_FILE = 'для бота.XLSX'


class BotWrapper:
    def __init__(self, token):
        self.token = token
        self.bot = None
        self._initialize_bot()

    def _initialize_bot(self):
        """Инициализация бота с обработкой ошибок"""
        max_retries = 3
        retry_delay = 5

        for attempt in range(max_retries):
            try:
                self.bot = telebot.TeleBot(self.token)
                # Проверяем соединение
                self.bot.get_me()
                logger.info("Бот успешно авторизован")
                return True
            except Exception as e:
                logger.error(f"Попытка {attempt + 1}: Ошибка инициализации бота - {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)

        logger.critical("Не удалось инициализировать бота. Проверьте токен")
        return False

    def polling(self):
        """Запуск бота с обработкой ошибок"""
        while True:
            try:
                logger.info("Запуск бота...")
                self.bot.polling(none_stop=True, interval=3, timeout=60)
            except Exception as e:
                logger.error(f"Ошибка в работе бота: {e}")
                time.sleep(10)
                continue


# Создаем экземпляр бота
bot_wrapper = BotWrapper(TELEGRAM_TOKEN)
bot = bot_wrapper.bot if bot_wrapper.bot else None


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
        logger.info(f"📂 Загружаю Excel-файл {EXCEL_FILE}...")
        if not os.path.exists(EXCEL_FILE):
            logger.error(f"Файл {EXCEL_FILE} не найден.")
            return None

        df_local = pd.read_excel(EXCEL_FILE, sheet_name=0)
        df_local = df_local.astype(str)

        # Создаем два столбца для поиска
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
        lines = user_input.split('\n')
        all_potential_compound_articles = []
        all_potential_simple_articles = []

        for line in lines:
            compound_pattern = r'\b\d{2,5}(?:\s+\d{1,5}){1,3}\b'
            potential_compound_articles = re.findall(compound_pattern, line)
            all_potential_compound_articles.extend(potential_compound_articles)

            simple_pattern = r'\b\d{4,}\b'
            potential_simple_articles = re.findall(simple_pattern, line)
            all_potential_simple_articles.extend(potential_simple_articles)

        # Нормализация и обработка артикулов
        normalized_compound = [normalize_with_spaces(c) for c in all_potential_compound_articles]
        for compound in all_potential_compound_articles:
            for part in re.findall(r'\d+', compound):
                if part in all_potential_simple_articles:
                    all_potential_simple_articles.remove(part)

        normalized_simple = [normalize(c) for c in all_potential_simple_articles]
        all_candidates = normalized_simple + normalized_compound

        if not all_candidates:
            return "⛔️ Не найден ни один артикул в сообщении."

        # Поиск в базе данных
        found_rows = pd.DataFrame()
        found_articles = []
        not_found_articles = []

        for candidate in normalized_compound:
            matches = df_data[df_data['Артикул_with_spaces'] == candidate]
            if not matches.empty:
                found_rows = pd.concat([found_rows, matches])
                found_articles.append(candidate)
            else:
                not_found_articles.append(candidate)

        for candidate in normalized_simple:
            matches = df_data[df_data['Артикул_clean'] == candidate]
            if not matches.empty:
                found_rows = pd.concat([found_rows, matches])
                found_articles.append(candidate)
            else:
                not_found_articles.append(candidate)

        if found_rows.empty:
            return "❌ Ни один артикул не найден в базе."

        unique_rows = found_rows.drop_duplicates(subset='Артикул', keep='first')

        # Формирование ответа
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

        if not_found_articles:
            reply += f"\n\n⚠️ Не найдены в базе: {', '.join(not_found_articles)}"

        return reply
    except Exception as e:
        logger.error(f"Ошибка при поиске: {e}")
        return "⚠️ Произошла ошибка при поиске. Попробуйте позже."


@bot.message_handler(commands=['start', 'help'])
def handle_start_help(message):
    help_text = (
        "🔍 *Бот для поиска товаров по артикулу (Excel-база)*\n\n"
        "Отправьте мне артикул товара — и я найду его в базе.\n"
        "Примеры:\n"
        "`805015`\n"
        "`где 805015 и 805017`\n"
        "`код 3546945`\n"
        "`3222 3390 07`\n"
        "`3128 0619 00`\n"
    )
    try:
        bot.send_message(message.chat.id, help_text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")


@bot.message_handler(commands=['reload'])
def handle_reload(message):
    global df
    try:
        bot.send_message(message.chat.id, "🔄 Перезагружаю Excel-базу...")
        df = load_database()
        if df is not None:
            bot.send_message(message.chat.id, f"✅ База загружена. Записей: {len(df)}")
        else:
            bot.send_message(message.chat.id, "❌ Не удалось загрузить Excel-базу.")
    except Exception as e:
        logger.error(f"Ошибка при перезагрузке базы: {e}")
        bot.send_message(message.chat.id, "⚠️ Ошибка при перезагрузке базы.")


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        user_text = message.text
        logger.info(f"Запрос от {message.from_user.id}: {user_text}")
        bot.send_chat_action(message.chat.id, 'typing')
        reply = find_best_matches(user_text, df)

        for i in range(0, len(reply), 4000):
            try:
                bot.send_message(message.chat.id, reply[i:i + 4000])
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения: {e}")
                continue

    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}")
        try:
            bot.send_message(message.chat.id, "⚠️ Ошибка при обработке запроса.")
        except:
            pass


if __name__ == "__main__":
    if bot:
        # Запускаем проверку почты в отдельном потоке
        mail_thread = Thread(target=run_scheduled_check, daemon=True)
        mail_thread.start()

        # Загружаем базу данных
        df = load_database()

        if df is not None:
            logger.info("✅ Excel-бот запущен и ждёт запросы...")
            # Запускаем бота
            bot_wrapper.polling()
        else:
            logger.error("❌ Не удалось загрузить базу данных. Бот не запущен.")
    else:
        logger.error("❌ Бот не инициализирован. Проверьте токен.")