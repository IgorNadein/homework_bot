import json
import logging
import os
import time
from http import HTTPStatus
from logging.handlers import RotatingFileHandler

import requests
from dotenv import load_dotenv
from telebot import TeleBot, apihelper


load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
DUPLICATE_DELAY = 3600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

STATUS_CHANGE_MSG = 'Изменился статус проверки работы "{}". {}'

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.',
}

sent_errors = {}


class APIRequestError(Exception):
    """Custom exception for API request errors."""


class APIResponseError(Exception):
    """Custom exception for API response errors."""


class HomeworkStatusError(Exception):
    """Custom exception for homework status errors."""


class TokenError(Exception):
    """Custom exception for token validation errors."""


def configure_logging(
        log_file=__file__ + '.log',
        level=logging.INFO,
        maxBytes=5 * 1024 * 1024,
        backupCount=5
):
    """Настройки систему ведения."""
    log_format = (
        '%(asctime)s, %(levelname)s, %(message)s,'
        '%(name)s, %(lineno)d, %(funcName)s'
    )
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=maxBytes,
        backupCount=backupCount
    )
    file_handler.setFormatter(logging.Formatter(log_format))

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(log_format))

    logger = logging.getLogger(__name__)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.setLevel(level)


def check_tokens():
    """Проверяет доступность переменных окружения."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }
    missing = [key for key, value in tokens.items() if value is None]
    if missing:
        message = (
            f'Отсутствуют необходимые переменные окружения: '
            f'{", ".join(missing)}'
        )
        logging.critical(message)
        raise TokenError(message)


def get_api_answer(timestamp):
    """Делает запрос к API и возвращает ответ."""
    payload = {'from_date': timestamp}
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=payload
        )
        if response.status_code != HTTPStatus.OK.value:
            logging.exception('Ошибка запроса к API')
            raise APIRequestError(
                f'Ошибка запроса к API\n'
                f'HTTP Status Code: {response.status_code}'
                f'Конечная точка: {ENDPOINT}\n'
                f'Заголовки: {HEADERS}\n'
                f'Параметры: {payload}'
            )
    except requests.exceptions.RequestException as e:
        error_message = (
            f'Ошибка запроса к API: {e}\n'
            f'HTTP Status Code: {getattr(response, "status_code", "N/A")}\n'
            f'Конечная точка: {ENDPOINT}\n'
            f'Заголовки: {HEADERS}\n'
            f'Параметры: {payload}'
        )
        logging.exception(error_message)
        raise APIRequestError(error_message) from e
    try:
        data = response.json()
        if 'code' in data and data['code'] != HTTPStatus.OK.value:
            raise APIRequestError(
                f'API error: {data.get("error", "Unknown error")}'
                f'код: {data["code"]}'
            )
        if 'error' in data:
            raise APIRequestError(f'API error: {data["error"]}')
    except json.JSONDecodeError:
        error_message = f'Ошибка декодирования JSON ответа: {response.text}'
        logging.exception(error_message)
        raise APIRequestError(error_message)
    return data


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not response:
        raise APIResponseError('Ответ API пуст или  None.')
    if not isinstance(response, dict):
        response_type = type(response)
        error_message = (
            f'Ответ API не является словарем.'
            f'Получен объект типа: {response_type}.\n'
            f'Значение ответа: {response}'
        )
        raise TypeError(error_message)
    if 'homeworks' not in response:
        raise APIResponseError('Ответ API не содержит ключ "homeworks".')
    if not isinstance(response['homeworks'], list):
        response_type = type(response['homeworks'])
        error_message = (
            f'Ответ API по ключу "homeworks" не является списком.'
            f'Получен объект типа: {response_type}.\n'
            f'Значение ответа: {response["homeworks"]}'
        )
        raise TypeError(error_message)


def parse_status(homework):
    """Извлекает статус домашней работы."""
    if 'status' not in homework:
        raise HomeworkStatusError(
            'Ключ "status" отсутствует в данных homework.'
        )
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise KeyError(
            f'Unknown or missing status: {homework.get("status", "N/A")}')
    verdict = HOMEWORK_VERDICTS[status]
    if 'homework_name' in homework:
        name = homework['homework_name']
    return STATUS_CHANGE_MSG.format(name, verdict)


def send_message(bot, message):
    """Отправляет сообщение в Telegram-чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)

        logging.debug(f'Сообщение отправлено в Telegram: {message}')
    except apihelper.ApiException as e:
        logging.error(f'Ошибка отправки сообщения в Telegram {message}: {e}')


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())

    while True:
        try:
            response = get_api_answer(timestamp)
            check_response(response)
            if 'current_date' in response:
                timestamp = int(response['current_date']) + 1
            homeworks = response['homeworks']
            if homeworks:
                message = parse_status(homeworks[0])
                send_message(bot, message)
            else:
                logging.debug(
                    'В ответе API получен пустой список домашних работ')

        except Exception as e:
            error_message = str(e)
            if error_message not in sent_errors or time.time() - sent_errors[error_message] > DUPLICATE_DELAY:
                sent_errors[error_message] = time.time()
                message = f'Сбой в работе программы: {error_message}'
                send_message(bot, message)

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    configure_logging()
    main()
