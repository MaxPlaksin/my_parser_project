import telebot
import pandas as pd

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = '7136103155:AAHS8y4z7CsdSpddDddU6p60TM8dTFElXmY'

# === ЗАГРУЗКА EXCEL-БАЗЫ ===
print("📂 Загружаю Excel-файл...")
df = pd.read_excel('Остатки (1).xlsx', sheet_name='TDSheet')
df = df.dropna(subset=['Номенклатура', 'Артикул'])
df = df.astype(str)

# Чистим артикулы от пробелов для поиска
df['Артикул_clean'] = df['Артикул'].str.replace(" ", "").str.lower()

# === ИНИЦИАЛИЗАЦИЯ БОТА ===
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# === ПОИСК ПО АРТИКУЛАМ ===
import re

def find_best_matches(user_input):
    # 1. Извлекаем все потенциальные артикулы (5+ цифр подряд, с пробелами)
    raw_matches = re.findall(r'[\d\s]{5,15}', user_input)
    cleaned_inputs = [x.replace(" ", "").lower() for x in raw_matches if len(x.strip()) >= 5]

    if not cleaned_inputs:
        return "⛔️ В сообщении не найден ни один артикул."

    # 2. Сравниваем с очищенной базой
    df['Артикул_clean'] = df['Артикул'].astype(str).str.replace(" ", "").str.lower()
    found_rows = df[df['Артикул_clean'].isin(cleaned_inputs)]

    if found_rows.empty:
        return "❌ Ни один артикул не найден в базе."

    # 3. Убираем дубликаты
    unique_rows = found_rows.drop_duplicates(subset='Артикул_clean', keep='first')

    results = []
    for _, row in unique_rows.iterrows():
        results.append(
            f"📦 Артикул: {row['Артикул']}\n"
            f"Наименование: {row.get('Номенклатура', '—')}\n"
            f"Код: {row.get('Номенклатура.Код', '—')}\n"
            f"Склад: {row.get('Склад', '—')}\n"
            f"Остаток: {row.get('Остаток', '—')}\n"
            f"Цена: {row.get('Цена', '—')} {row.get('Валюта', '')}\n"
        )

    return "\n".join(results[:10]) + ("\n...и т.д." if len(results) > 10 else "")


    found_rows = df[df['Артикул_clean'].isin(cleaned_inputs)]

    if found_rows.empty:
        return "Товары не найдены."

    # Убираем дубликаты по артикулу
    unique_rows = found_rows.drop_duplicates(subset='Артикул_clean', keep='first')

    results = []
    for _, row in unique_rows.iterrows():
        results.append(
            f"📦 Артикул: {row['Артикул']}\n"
            f"Наименование: {row.get('Номенклатура', '—')}\n"
            f"Код: {row.get('Номенклатура.Код', '—')}\n"
            f"Склад: {row.get('Склад', '—')}\n"
            f"Остаток: {row.get('Остаток', '—')}\n"
            f"Цена: {row.get('Цена', '—')} {row.get('Валюта', '')}\n"
        )

    return "\n".join(results[:10]) + ("\n...и т.д." if len(results) > 10 else "")

# === ОБРАБОТКА СООБЩЕНИЙ ОТ ПОЛЬЗОВАТЕЛЕЙ ===
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_text = message.text
    bot.send_chat_action(message.chat.id, 'typing')
    reply = find_best_matches(user_text)
    bot.reply_to(message, reply)

# === ЗАПУСК БОТА ===
print("✅ Бот запущен и ждёт запросы...")
bot.polling()
