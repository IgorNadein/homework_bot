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
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
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
    payload = {'from_date': timestamp - RETRY_PERIOD}
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=payload
        )
        response.raise_for_status()
        return response.json()
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
        return False
    if 'homeworks' in response and 'current_date' in response:
        if (
            len(response['homeworks']) > 0
            and 'lesson_name' in response['homeworks'][0]
            and 'status' in response['homeworks'][0]
        ) or len(response['homeworks']) == 0:
            return True
        else:
            logging.error(
                'Ключ "lesson_name" или "status" отсутствует в списке homework'
            )
    else:
        logging.error(
            'Ключ "homeworks" или "current_date" отсутствует в ответе API.'
        )
        return False


def parse_status(homework):
    """Извлекает статус домашней работы."""
    homework = homework['homeworks']
    if len(homework) > 0:
        homework = homework[0]
        homework_name = homework['lesson_name']
        verdict = HOMEWORK_VERDICTS[homework['status']]
        return f'Изменился статус проверки работы "{homework_name}". {verdict}'
    else:
        return None


def send_message(bot, message):
    """Отправляет сообщение в Telegram-чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.info(f"Сообщение отправлено в Telegram: {message}")
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
                message = parse_status(response)
                if message:
                    send_message(bot, message)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
