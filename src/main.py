import telebot
import pandas as pd
from fuzzywuzzy import fuzz

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = '7136103155:AAHS8y4z7CsdSpddDddU6p60TM8dTFElXmY'  # ← Твой токен Telegram-бота

# === ЗАГРУЗКА EXCEL-БАЗЫ ===
print("📂 Загружаю Excel-файл...")
df = pd.read_excel('Остатки (1).xlsx', sheet_name='TDSheet')
df = df.dropna(subset=['Номенклатура', 'Артикул'])
df = df[['Номенклатура', 'Артикул']].astype(str)

# === ПОДГОТОВКА СПИСКОВ ===
nomenclatures = df['Номенклатура'].tolist()
artikuls = df['Артикул'].tolist()

# === ИНИЦИАЛИЗАЦИЯ TELEGRAM-БОТА ===
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# === ПОИСК ПО БАЗЕ (ЧЁТКИЙ И ПО КЛЮЧЕВЫМ СЛОВАМ) ===
def find_best_matches(user_input):
    input_clean = user_input.replace(" ", "").lower()

    # === Проверка: это похоже на артикул?
    for idx, raw_artikul in enumerate(df['Артикул']):
        artikul_clean = raw_artikul.replace(" ", "").lower()
        if input_clean == artikul_clean:
            name = df.iloc[idx]['Номенклатура']
            return f"🔎 Найден артикул:\n{raw_artikul} — {name}"

    # === Если не найдено точное совпадение по артикулу — возвращаем "Товар не найден"
    return "Товар не найден."


    # === Точный поиск по артикулу ===
    for idx, raw_artikul in enumerate(df['Артикул']):
        artikul_clean = raw_artikul.replace(" ", "").lower()
        if input_clean == artikul_clean:
            name = df.iloc[idx]['Номенклатура']
            return f"🔎 Найден по артикулу:\n{raw_artikul} — {name}"

    # === Поиск по смыслу, как раньше ===
    threshold_main = 70
    threshold_partial = 60
    results = []

    for name, artikul in zip(df['Номенклатура'], df['Артикул']):
        score_full = fuzz.token_set_ratio(user_input.lower(), name.lower())
        if score_full >= threshold_main:
            results.append((artikul, score_full))
        else:
            words = user_input.lower().split()
            for word in words:
                if len(word) < 3:
                    continue
                score_partial = fuzz.partial_ratio(word, name.lower())
                if score_partial >= threshold_partial:
                    results.append((artikul, score_partial))
                    break

    if not results:
        return "Товар не найден."

    results = list(set(a for a, _ in results))[:30]
    reply = "🔍 Найдено (показано до 30 артикулов):\n" + "\n".join(results)
    if len(results) == 30:
        reply += "\n...возможно есть ещё, уточните запрос."
    return reply


    results = []

    for name, artikul in zip(nomenclatures, artikuls):
        score_full = fuzz.token_set_ratio(user_input.lower(), name.lower())
        if score_full >= threshold_main:
            results.append((artikul, score_full))
        else:
            words = user_input.lower().split()
            for word in words:
                if len(word) < 3:
                    continue
                score_partial = fuzz.partial_ratio(word, name.lower())
                if score_partial >= threshold_partial:
                    results.append((artikul, score_partial))
                    break

    if not results:
        return "Товар не найден."

    unique_artikuls = sorted(set(a for a, _ in results))
    max_results = 30  # максимум строк
    short_list = unique_artikuls[:max_results]
    reply = "🔍 Найдено (показано до 30 артикулов):\n" + "\n".join(short_list)
    if len(unique_artikuls) > max_results:
        reply += f"\n...и ещё {len(unique_artikuls) - max_results} результатов скрыто."
    return reply


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
