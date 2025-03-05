import time
import requests
from telegram.ext import Updater, CommandHandler
from threading import Thread
from flask import Flask, request
import json

# Конфигурация
API_KEY = "2364999c-427e-4cff-b4af-7cec2511069b"
TELEGRAM_TOKEN = "7535392226:AAHXAO7TJBG_59pDNwE3za6Vn-MRiZMRyW4"
TARGET_USER_ID = "5998116373"
BASE_URL = "https://mainnet.helius-rpc.com/?api-key="

# Динамический список монет
monitored_coins = {}

# Flask для Webhook
app = Flask(__name__)

# Запуск Flask в отдельном потоке
def run_flask():
    app.run(host='0.0.0.0', port=5000)

# Обработка Webhook для новых токенов
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if isinstance(data, list) and len(data) > 0:
        transaction = data[0]
        if 'meta' in transaction and 'postTokenBalances' in transaction['meta']:
            for balance in transaction['meta']['postTokenBalances']:
                token_address = balance.get('mint')
                if token_address and token_address not in monitored_coins:
                    monitored_coins[token_address] = {"holders": 0, "last_check": 0, "stagnation_time": 0}
                    print(f"Добавлен новый токен: {token_address}")
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
        return 0
    except Exception as e:
        print(f"Ошибка при запросе к API: {e}")
        return None

# Функция мониторинга
def monitor_coins(update_context):
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
                    update_context.bot.send_message(
                        chat_id=TARGET_USER_ID,
                        text=f"Начало мониторинга токена {token_address} с {current_holders} холдерами"
                    )
                    continue

                # Проверка изменения количества холдеров
                diff = current_holders - info["holders"]
                current_time = time.time()
                
                if diff >= 10 and diff <= 20:
                    update_context.bot.send_message(
                        chat_id=TARGET_USER_ID,
                        text=f"Монета {token_address}: количество холдеров увеличилось на {diff} (всего: {current_holders})"
                    )
                    info["holders"] = current_holders
                    info["stagnation_time"] = 0
                    info["last_check"] = current_time
                
                elif diff > 20:
                    info["holders"] = current_holders
                    info["stagnation_time"] = 0
                    info["last_check"] = current_time
                
                else:
                    # Проверка стагнации
                    elapsed_time = current_time - info["last_check"]
                    info["stagnation_time"] += elapsed_time
                    
                    if info["stagnation_time"] >= 10:
                        coins_to_remove.append(token_address)
                        update_context.bot.send_message(
                            chat_id=TARGET_USER_ID,
                            text=f"Монета {token_address} исключена из мониторинга: нет роста более 10 холдеров за 10 секунд"
                        )
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
    monitor_thread = Thread(target=monitor_coins, args=(context,))
    monitor_thread.start()

def main():
    # Запуск Flask в отдельном потоке
    flask_thread = Thread(target=run_flask)
    flask_thread.start()

    # Запуск Telegram бота
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()