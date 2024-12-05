import logging
import os
import time

import requests
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler
from telebot import TeleBot, apihelper


logging.basicConfig(
    level=logging.INFO,
    filename='homework.log',
    format='%(asctime)s, %(levelname)s, %(message)s, %(name)s'
)
logger = logging.getLogger(__name__)
handler = RotatingFileHandler('homework.log', maxBytes=50000000, backupCount=5)
logger.addHandler(handler)

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.',
}


def check_tokens():
    """Проверяет доступность переменных окружения."""
    tokens = [PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]
    if any(token is None for token in tokens):
        logging.critical("Отсутствуют необходимые переменные окружения.")
        return False
    else:
        return True


def get_api_answer(timestamp):
    """Делает запрос к API и возвращает ответ."""
    payload = {'from_date': timestamp}
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=payload
        )
        if response.status_code != 200:
            raise requests.exceptions.HTTPError
        return response.json()
    except requests.exceptions.HTTPError as e:
        logging.error(f"Ошибка запроса к API (HTTP Error): {e}")
        logging.error(f"HTTP Status Code: {e.response.status_code}")
        logging.error(f"API Response Text: {e.response.text}")
        return None
    except requests.exceptions.RequestException as e:
        logging.error(
            f'Ошибка при запросе к API сервиса Практикум Домашка: {e}')
        return None


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not response:
        return False
    if not isinstance(response, dict):
        logging.error('Ответ API не является словарем.')
        raise TypeError
    if 'homeworks' not in response or not isinstance(
            response['homeworks'], list
    ):
        logging.error('Ключ "homeworks" отсутствует или не является списком.')
        raise TypeError
    if 'current_date' not in response:
        logging.error('Ключ "current_date" отсутствует в ответе API.')
        return False
    return True


def parse_status(homework):
    """Извлекает статус домашней работы."""
    if 'status' not in homework or homework['status'] not in HOMEWORK_VERDICTS:
        raise KeyError(
            f"Unknown or missing status: {homework.get('status', 'N/A')}")
    verdict = HOMEWORK_VERDICTS[homework['status']]
    if 'homework_name' in homework:
        homework_name = homework['homework_name']
    else:
        homework_name = homework['lesson_name']

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def send_message(bot, message):
    """Отправляет сообщение в Telegram-чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)

        logging.debug(f"Сообщение отправлено в Telegram: {message}")
    except apihelper.ApiException as e:
        logging.error(f"Ошибка отправки сообщения в Telegram: {e}")


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        return

    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())

    while True:
        try:
            response = get_api_answer(timestamp)
            if check_response(response):
                if len(response['homeworks']) > 0:
                    message = parse_status(response['homeworks'][0])
                    if message:
                        send_message(bot, message)
                else:
                    logging.debug(
                        'В ответе API получен пустой список домашних работ')

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
