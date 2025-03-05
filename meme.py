import time
import requests
import os
from telegram.ext import Updater, CommandHandler
from threading import Thread
from flask import Flask, request
import json
import logging

# Логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Конфигурация
API_KEY = "2364999c-427e-4cff-b4af-7cec2511069b"
TELEGRAM_TOKEN = "7535392226:AAHXAO7TJBG_59pDNwE3za6Vn-MRiZMRyW4"
TARGET_USER_ID = "5998116373"
BASE_URL = "https://mainnet.helius-rpc.com/?api-key="

# Динамический список монет
monitored_coins = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": {"holders": 0, "last_check": 0, "stagnation_time": 0},  # USDC
    "So11111111111111111111111111111111111111112": {"holders": 0, "last_check": 0, "stagnation_time": 0},  # Wrapped SOL
}

# Flask для Webhook (Helius и Telegram)
app = Flask(__name__)

# Обработка Telegram Webhook
@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    update = request.get_json()
    updater.bot.process_update(update)
    return '', 200

# Обработка Helius Webhook
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    logging.info(f"Получены данные от Helius: {json.dumps(data, indent=2)}")
    if isinstance(data, list) and len(data) > 0:
        transaction = data[0]
        if 'meta' in transaction and 'postTokenBalances' in transaction['meta']:
            for balance in transaction['meta']['postTokenBalances']:
                token_address = balance.get('mint')
                if token_address and token_address not in monitored_coins:
                    monitored_coins[token_address] = {"holders": 0, "last_check": 0, "stagnation_time": 0}
                    logging.info(f"Добавлен новый токен: {token_address}")
                    updater.bot.send_message(
                        chat_id=TARGET_USER_ID,
                        text=f"Добавлен новый токен: {token_address}"
                    )
    return '', 200

# Функция для получения количества холдеров
def get_holders_count(token_address):
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccounts",
            "params": {"mint": token_address}
        }
        response = requests.post(BASE_URL + API_KEY, json=payload)
        data = response.json()
        if "result" in data and "token_accounts" in data["result"]:
            return len(data["result"]["token_accounts"])
        logging.warning(f"Нет данных о холдерах для {token_address}: {data}")
        return 0
    except Exception as e:
        logging.error(f"Ошибка при запросе к API для {token_address}: {e}")
        return None

# Функция мониторинга
def monitor_coins():
    while True:
        coins_to_remove = []
        for token_address, info in monitored_coins.items():
            if token_address in monitored_coins:
                current_holders = get_holders_count(token_address)
                if current_holders is None:
                    continue
                
                # Первоначальная инициализация
                if info["holders"] == 0:
                    info["holders"] = current_holders
                    info["last_check"] = time.time()
                    updater.bot.send_message(
                        chat_id=TARGET_USER_ID,
                        text=f"Начало мониторинга токена {token_address} с {current_holders} холдерами"
                    )
                    logging.info(f"Начало мониторинга токена {token_address} с {current_holders} холдерами")
                    continue

                # Проверка изменения количества холдеров
                diff = current_holders - info["holders"]
                current_time = time.time()
                elapsed_time = current_time - info["last_check"]
                
                # Проверяем каждые 10-20 секунд
                if elapsed_time >= 10:  # Проверяем каждые 10 секунд
                    if diff >= 10 and diff <= 20:
                        updater.bot.send_message(
                            chat_id=TARGET_USER_ID,
                            text=f"Монета {token_address}: количество холдеров увеличилось на {diff} (всего: {current_holders}) за {int(elapsed_time)} секунд"
                        )
                        logging.info(f"Монета {token_address}: количество холдеров увеличилось на {diff} (всего: {current_holders})")
                        info["holders"] = current_holders
                        info["stagnation_time"] = 0
                        info["last_check"] = current_time
                    
                    elif diff > 20:
                        info["holders"] = current_holders
                        info["stagnation_time"] = 0
                        info["last_check"] = current_time
                    
                    else:
                        # Проверка стагнации
                        info["stagnation_time"] += elapsed_time
                        if info["stagnation_time"] >= 20:  # Исключаем, если нет роста за 20 секунд
                            coins_to_remove.append(token_address)
                            updater.bot.send_message(
                                chat_id=TARGET_USER_ID,
                                text=f"Монета {token_address} исключена из мониторинга: нет роста более 10 холдеров за 20 секунд"
                            )
                            logging.info(f"Монета {token_address} исключена из мониторинга")
                        info["last_check"] = current_time

        # Удаление монет после итерации
        for coin in coins_to_remove:
            if coin in monitored_coins:
                del monitored_coins[coin]

        time.sleep(1)  # Учитываем лимит бесплатного тарифа 1 запрос/сек

# Команда старта бота
def start(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text="Бот запущен! Мониторинг начался.")
    # Запуск мониторинга в отдельном потоке
    monitor_thread = Thread(target=monitor_coins)
    monitor_thread.start()

# Команда для проверки статуса
def status(update, context):
    if not monitored_coins:
        context.bot.send_message(chat_id=update.effective_chat.id, text="Нет токенов в мониторинге.")
    else:
        message = "Текущие токены в мониторинге:\n"
        for token_address, info in monitored_coins.items():
            message += f"{token_address}: {info['holders']} холдеров\n"
        context.bot.send_message(chat_id=update.effective_chat.id, text=message)

# Настройка Telegram бота
updater = Updater(TELEGRAM_TOKEN, use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("status", status))

# Запуск Flask
if __name__ == "__main__":
    # Настройка Telegram Webhook
    render_url = os.getenv("RENDER_EXTERNAL_URL", "https://your-app-name.onrender.com")  # Замените на ваш Render URL
    telegram_webhook_url = f"{render_url}/telegram"
    updater.bot.set_webhook(url=telegram_webhook_url)
    logging.info(f"Telegram Webhook установлен: {telegram_webhook_url}")

    # Запуск мониторинга
    monitor_thread = Thread(target=monitor_coins)
    monitor_thread.start()

    # Запуск Flask
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
