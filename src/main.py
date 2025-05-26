import telebot
import pandas as pd
import re

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = '7136103155:AAHS8y4z7CsdSpddDddU6p60TM8dTFElXmY'

# === ЗАГРУЗКА EXCEL-БАЗЫ ===
print("📂 Загружаю Excel-файл...")
df = pd.read_excel('Остатки (1).xlsx', sheet_name='TDSheet')
df = df.dropna(subset=['Номенклатура', 'Артикул'])
df = df.astype(str)

# === ИНИЦИАЛИЗАЦИЯ БОТА ===
bot = telebot.TeleBot(TELEGRAM_TOKEN)

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
def find_best_matches(user_input):
    keywords = ['артикул', 'арт', 'код', 'поз', 'позиция', 'номер']
    text = user_input.lower()

    # 1. Ищем артикулы после ключевых слов
    pattern = r'(' + '|'.join(keywords) + r')\s*[:\-]?\s*([\w\s\-\/]{4,})'
    matches = re.findall(pattern, text)
    cleaned_inputs = [normalize(m[1]) for m in matches if len(m[1].strip()) >= 4]

    # 2. Если не нашли — fallback: всё, что похоже на артикул
    if not cleaned_inputs:
        raw_matches = re.findall(r'[\w\/\-]{4,}', text)
        cleaned_inputs = [normalize(x) for x in raw_matches]

    if not cleaned_inputs:
        return "⛔️ В сообщении не найден ни один артикул."

    # 3. Подготовим базу
    df['Артикул_clean'] = df['Артикул'].apply(normalize)
    found_rows = df[df['Артикул_clean'].isin(cleaned_inputs)]

    if found_rows.empty:
        return "❌ Ни один артикул не найден в базе."

    # 4. Убираем дубликаты
    unique_rows = found_rows.drop_duplicates(subset='Артикул_clean', keep='first')

    # 5. Собираем результат
    results = []
    for _, row in unique_rows.iterrows():
        price = str(row.get('Цена', '')).strip()
        currency = str(row.get('Валюта', '')).strip()
        price_text = "нет" if not price or price.lower() == 'nan' else f"{price} {currency}".strip()

        results.append(
            f"📦 Артикул: {row['Артикул']}\n"
            f"Наименование: {row.get('Номенклатура', '—')}\n"
            f"Код: {row.get('Номенклатура.Код', '—')}\n"
            f"Склад: {row.get('Склад', '—')}\n"
            f"Остаток: {row.get('Остаток', '—')}\n"
            f"Цена: {price_text}\n"
        )

    return "\n".join(results[:20]) + ("\n...и т.д." if len(results) > 20 else "")

# === ОБРАБОТКА СООБЩЕНИЙ ОТ ПОЛЬЗОВАТЕЛЕЙ ===
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_text = message.text
    bot.send_chat_action(message.chat.id, 'typing')
    reply = find_best_matches(user_text)
    bot.reply_to(message, reply)

# === ЗАПУСК ===
print("✅ Бот запущен и ждёт запросы...")
bot.polling()
