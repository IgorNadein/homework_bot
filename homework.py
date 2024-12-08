import logging
import os
import sys
import time
from http import HTTPStatus
from logging.handlers import RotatingFileHandler

import requests
from dotenv import load_dotenv
from telebot import TeleBot, apihelper


load_dotenv()

logger = logging.getLogger(__name__)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TOKENS = (
    'PRACTICUM_TOKEN',
    'TELEGRAM_TOKEN',
    'TELEGRAM_CHAT_ID',
)

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

STATUS_CHANGE = 'Изменился статус проверки работы "{}". {}'
NO_DATA_AVAILABLES_CHANGE = ' Ключ {} отсутствует в данных {}.'
API_REQUEST_ERROR = 'Ошибка запроса к API: {}, Request parameters: {}.'
API_RESPONSE_ERROR = 'Ответ API: {}, ожидается: {}.'
ERROR_MESSAGE = 'Ошибка отправки сообщения в Telegram {}: {}'
MESSAGE_SENT = 'Сообщение отправлено в Telegram: {}'
NUL_LIST_ERROR = 'В ответе API получен пустой список домашних работ или None'
PROGRAM_ERROR = 'Сбой в работе программы: {}'

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.',
}


class APIResponseError(Exception):
    """Custom exception for API response errors."""


def check_tokens():
    """Проверяет доступность переменных окружения."""
    missings = [token for token in TOKENS if globals()[token] is None]
    if missings:
        message = (
            f'Отсутствуют необходимые переменные окружения: {missings}'
        )
        logging.critical(message)
        raise KeyError(message)


def get_api_answer(timestamp):
    """Делает запрос к API и возвращает ответ."""
    requests_pars = dict(
        url=ENDPOINT,
        headers=HEADERS,
        params={'from_date': timestamp}
    )
    try:
        response = requests.get(**requests_pars)
    except requests.RequestException as e:
        raise ConnectionError(API_REQUEST_ERROR.format(e, **requests_pars))

    if response.status_code != HTTPStatus.OK.value:
        raise requests.exceptions.HTTPError(
            API_REQUEST_ERROR.format(response.status_code, **requests_pars)
        )

    data = response.json()
    for key in ('code', 'error'):
        if key in data:
            raise ValueError(
                API_REQUEST_ERROR.format(key, data[key])
            )

    return data


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not response:
        raise ConnectionError(NUL_LIST_ERROR)
    if not isinstance(response, dict):
        raise TypeError(
            API_RESPONSE_ERROR.format(type(response), type(dict()))
        )
    if 'homeworks' not in response:
        raise APIResponseError(
            API_RESPONSE_ERROR.format(type(None), 'homeworks')
        )
    if not isinstance(response['homeworks'], list):
        raise TypeError(
            API_RESPONSE_ERROR.format(
                type(response['homeworks']), type(list())
            )
        )


def parse_status(homework):
    """Извлекает статус домашней работы."""
    if 'status' not in homework:
        raise AttributeError(
            NO_DATA_AVAILABLES_CHANGE.format('status', 'homework')
        )
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(
            NO_DATA_AVAILABLES_CHANGE.format(status, 'HOMEWORK_VERDICTS')
        )
    if 'homework_name' in homework:
        name = homework['homework_name']
    return STATUS_CHANGE.format(name, HOMEWORK_VERDICTS[status])


def send_message(bot, message):
    """Отправляет сообщение в Telegram-чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.debug(MESSAGE_SENT.format(message))
        return True
    except apihelper.ApiException as e:
        logging.error(ERROR_MESSAGE.format({message}, {e}))
        return False


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    error_message = None

    while True:
        try:
            response = get_api_answer(timestamp)
            check_response(response)
            homeworks = response['homeworks']
            if homeworks:
                message = parse_status(homeworks[0])
                telegram_send_success = send_message(bot, message)
                if telegram_send_success:
                    timestamp = int(
                        response.get('current_date')
                    )
            else:
                logging.debug(NUL_LIST_ERROR)

        except Exception as e:
            if str(e) != error_message:
                send_message(bot, message)
                error_message = str(e)
            logging.error(PROGRAM_ERROR.format(error_message))

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format=(
            '%(asctime)s, %(levelname)s, %(name)s, '
            '%(lineno)d, %(funcName)s, %(message)s'
        ),
        handlers=[
            RotatingFileHandler(f'{__file__}.log',
                                maxBytes=5 * 1024 * 1024, backupCount=5),
            logging.StreamHandler(stream=sys.stdout),
        ],
    )
    main()
