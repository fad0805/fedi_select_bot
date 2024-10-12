import functools
from lxml import html
import logging
import logging.config
import os
import random
import re
import mastodon as mstdn
from mastodon import Mastodon
from mastodon import StreamListener

CLIENT_KEY = os.getenv('CLIENT_KEY')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')

logger = logging.getLogger(__name__)
rules = "물음표(?) 뒤에 있는 문장을 띄어쓰기나 엔터, vs로 구분해서 선택해줍니다. \
'예아니오', '네아니오' 혹은 '네니오'가 들어있으면 ? 유무와 상관없이 네, 아니오로 대답합니다.\n \
(숫자)d(숫자)로 멘션 시 주사위를 굴려줍니다."


def roll_dice(origin):
    origin = origin.lower().split('d')

    count = ''
    for i in origin[0]:
        if not i.isdigit():
            break
        count = count + i

    dice = ''
    for i in origin[1]:
        if not i.isdigit():
            break
        dice = dice + i

    choices = []
    for i in range(int(count)):
        dice_number = [i for i in range(1, int(dice) + 1)]
        choices.append(str(random.choice(dice_number)))

    result = ', '.join(choices)
    if len(result) > 500:
        result = '주사위를 너무 많이 굴렸습니다. 500자를 넘어가면 출력할 수 없습니다.'
    return result


def select(origin):
    if '네니오' in origin or '네아니오' in origin:
        return random.choice(['네', '아니오'])
    elif '예아니오' in origin:
        return random.choice(['예', '아니오'])

    elif re.search(r'\d[dD]\d', origin):
        return roll_dice(origin)

    if origin.endswith('?') is False and '?' in origin:
        origin = origin.split('?')[1]

    origin = origin.strip()

    choices = []
    if 'vs' in origin.lower():
        choices = origin.lower().split('vs')
    elif '\n' in origin:
        choices = origin.split('\n')
    else:
        choices = origin.split(' ')

    if '' in choices:
        choices.remove('')

    if len(choices) == 0:
        return rules

    return random.choice(choices).strip()


class MyListener(StreamListener):
    def __init__(self, api: Mastodon):
        super().__init__()
        self.api = api
        self.logger = logging.getLogger('selectbot')
        self.me = self.api.account_verify_credentials()
        self.logger.info(f'I am {self.me["acct"]}')

    def on_notification(self, notification):
        if notification['type'] == 'mention':
            account = notification['account']
            status = notification['status']
            content = self.get_plain_content(status)
            self.logger.info(f'{account["acct"]} mentioned me with {content}')
            self.handle_status(status)
        else:
            self.logger.info(f'Unhandeled notification: {notification["type"]}')

    def handle_status(self, status):
        if status['reblog'] is not None:
            self.logger.debug('Skipping reblogged status.')
            return

        account = status['account']
        content = self.get_plain_content(status)

        for mention in status['mentions']:
            if mention['id'] == self.me['id']:
                self.logger.debug(f'{account["acct"]}: {content}')
                self.logger.info(f'Replying to {account["acct"]}')
                self.reply(status)

    def reply(self, status):
        logger.info(f'Replying to {status["account"]["acct"]}')
        visibility = status['visibility']
        if visibility == 'public':
            visibility = 'unlisted'

        mention = ''.join(
            f'@{user["acct"]} '
            for user in [status['account']] + status['mentions']
            if user['acct'] != self.me['acct']
        )

        content = self.get_plain_content(status)

        self.api.status_post(
            f'{mention}{select(content)}',
            in_reply_to_id=status['id'],
            visibility=visibility
        )

    @staticmethod
    def get_plain_content(status):
        if not status['content']:
            return ''
        doc = html.fromstring(status['content'])
        for link in doc.xpath('//a'):
            link.drop_tree()

        # Fix br into \n
        for br in doc.xpath('//br'):
            br.tail = '\n' + (br.tail or '')

        content = doc.text_content()
        return content.strip()

    @property
    def stream_user(self):
        return functools.partial(self.api.stream_user, self)

    @property
    def stream_local(self):
        return functools.partial(self.api.stream_local, self)

    @property
    def stream_public(self):
        return functools.partial(self.api.stream_public, self)

    @property
    def stream_hashtag(self):
        return functools.partial(self.api.stream_hashtag, self)


def set_logger():
    logging.config.fileConfig('logging.conf')


def make_streaming():
    try:
        api = Mastodon(
            api_base_url='https://daydream.ink',
            client_id=CLIENT_KEY,
            client_secret=CLIENT_SECRET,
            access_token=ACCESS_TOKEN,
        )
        stream = MyListener(api)
    except Exception as e:
        logger.error(e)
    else:
        return stream


def main():
    set_logger()

    mastodon = make_streaming()
    logger.info("Start selectbot")
    mastodon.stream_user(reconnect_async=True)


if __name__ == "__main__":
    while True:
        try:
            main()
        except mstdn.errors.MastodonNetworkError:
            pass
        except Exception as e:
            print(e)
