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


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
tokens = {
    'PRACTICUM_TOKEN',
    'TELEGRAM_TOKEN',
    'TELEGRAM_CHAT_ID',
}

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

STATUS_CHANGE_MSG = 'Изменился статус проверки работы "{}". {}'
NO_DATA_AVAILABLES_CHANGE_MSG = ' Ключ {} отсутствует в данных {}.'
API_REQUEST_ERROR_MESSAGE = 'Ошибка запроса к API: {}, Request parameters: {}.'
API_RESPONSE_ERROR_MESSAGE = 'Ответ API: {}, ожидается: {}.'
ERROR_MESSAGE = 'Ошибка отправки сообщения в Telegram {}: {}'
MESSAGE_SENT = 'Сообщение отправлено в Telegram: {}'
NUL_LIST_ERROR_MESSAGE = 'В ответе API получен пустой список домашних работ'
PROGRAM_ERROR_MESSAGE = 'Сбой в работе программы: {}'

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.',
}


class APIResponseError(Exception):
    """Custom exception for API response errors."""


class TokenError(Exception):
    """Custom exception for token validation errors."""


def check_tokens():
    """Проверяет доступность переменных окружения."""
    missings = [token for token in tokens if globals()[token] is None]
    if missings:
        message = (
            f'Отсутствуют необходимые переменные окружения: {missings}'
        )
        logging.critical(message)
        raise TokenError(message)


def get_api_answer(timestamp):
    """Делает запрос к API и возвращает ответ."""
    rq_pars = dict(
        url=ENDPOINT,
        headers=HEADERS,
        params={'from_date': timestamp}
    )
    try:
        response = requests.get(**rq_pars)
    except requests.RequestException as e:
        raise ConnectionError(API_REQUEST_ERROR_MESSAGE.format(e, **rq_pars))

    if response.status_code != HTTPStatus.OK.value:
        raise ConnectionError(
            API_REQUEST_ERROR_MESSAGE.format(ConnectionError, **rq_pars)
            + f' HTTP Status Code: {response.status_code}'
        )

    data = response.json()
    for key in ('code', 'error'):
        if key in data:
            error_details = f'В json() обнаружен ключ {key}: {data[key]}'
            raise ConnectionError(
                API_REQUEST_ERROR_MESSAGE.format(error_details, **rq_pars)
            )

    return data


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not response:
        raise APIResponseError(
            API_RESPONSE_ERROR_MESSAGE.format('None или пуст', 'dict')
        )
    if not isinstance(response, dict):
        raise TypeError(
            API_RESPONSE_ERROR_MESSAGE.format(type(response), 'dict')
        )
    if 'homeworks' not in response:
        raise APIResponseError(
            API_RESPONSE_ERROR_MESSAGE.format('None', 'homeworks')
        )
    if not isinstance(response['homeworks'], list):
        response_type = type(response['homeworks'])
        raise TypeError(
            API_RESPONSE_ERROR_MESSAGE.format(
                f'"homeworks" type = {response_type}', 'list'
            )
        )


def parse_status(homework):
    """Извлекает статус домашней работы."""
    if 'status' not in homework:
        raise ValueError(
            NO_DATA_AVAILABLES_CHANGE_MSG.format('status', 'homework')
        )
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(
            NO_DATA_AVAILABLES_CHANGE_MSG.format(status, 'HOMEWORK_VERDICTS')
        )
    if 'homework_name' in homework:
        name = homework['homework_name']
    return STATUS_CHANGE_MSG.format(name, HOMEWORK_VERDICTS[status])


def send_message(bot, message):
    """Отправляет сообщение в Telegram-чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.debug(MESSAGE_SENT.format(message))
    except apihelper.ApiException as e:
        logging.error(ERROR_MESSAGE.format({message}, {e}))


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
                send_message(bot, message)
                timestamp = int(response.get('current_date'))
            else:
                logging.debug(NUL_LIST_ERROR_MESSAGE)

        except Exception as e:
            if str(e) != error_message:
                error_message = str(e)
                send_message(bot, message)
            logging.error(PROGRAM_ERROR_MESSAGE.format(error_message))

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
    logger = logging.getLogger(__name__)
    main()
