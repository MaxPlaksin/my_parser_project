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
    if pd.isna(text):
        return ''
    text = str(text).strip()
    text = text.replace('\xa0', '').replace('\u202f', '')
    text = re.sub(r'[\s/-]', '', text)
    if text.endswith('.0'):
        text = text[:-2]
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
        df_local['Артикул_clean'] = df_local['Артикул'].apply(normalize)

        logger.info(f"✅ База успешно загружена. Записей: {len(df_local)}")
        return df_local
    except Exception as e:
        logger.error(f"Ошибка при загрузке базы: {e}")
        return None

def find_best_matches(user_input, df_data):
    if df_data is None:
        return "⚠️ База не загружена. Используйте /reload или обратитесь к администратору."

    try:
        raw_candidates = re.findall(r'[\w/-]{4,}', user_input)
        cleaned_inputs = list(set([normalize(x) for x in raw_candidates if x.strip()]))

        if not cleaned_inputs:
            return "⛔️ Не найден ни один артикул в сообщении."

        found_rows = df_data[df_data['Артикул_clean'].isin(cleaned_inputs)]

        if found_rows.empty:
            return "❌ Ни один артикул не найден в базе."

        unique_rows = found_rows.drop_duplicates(subset='Артикул_clean', keep='first')

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
        "`2657 2169 13`\n"
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
            bot.send_message(message.chat.id, reply[i:i+4000])

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
