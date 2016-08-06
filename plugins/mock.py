import random
from cloudbot import hook
from tinydb import TinyDB, Query


class MarkovChain(object):

    def __init__(self):
        self.chain_dict = {}

    def learn(self, words=None):
        words = words.replace("!", ".")
        words = words.replace("?", ".")
        while ".." in words:
            words = words.replace("..", ".")
        for sentence in words.split("."):
            if len(sentence.split(" ")) > 3:
                self.add_sentence(sentence)

    def add_sentence(self, sentence=None):
        sentence = self.clean(sentence)
        pre1, pre2 = ".", "."
        for word in sentence.split(" "):
            combined = "{} {}".format(pre1, pre2)
            if 'http' not in word:
                self.add_relationship(combined, word)
                pre1, pre2 = pre2, word

        combined = "{} {}".format(pre1, pre2)
        word = "."
        self.add_relationship(combined, word)

    def add_relationship(self, combined, word):
        if not self.chain_dict.get(combined, None):
            self.chain_dict[combined] = {}

        if self.chain_dict[combined].get(word, None):
            self.chain_dict[combined][word] += 1
        else:
            self.chain_dict[combined][word] = 1


    def clean(self, sentence=None):
        sentence = sentence.lower()
        regex = re.compile('[^a-z\s]')
        sentence = regex.sub('', sentence)
        return sentence

    def gen_text(self, sent_max=1):
        pre1, pre2 = ".", "."
        sent_count = 0
        output = ""
        while sent_count < sent_max:
            combined = "{} {}".format(pre1, pre2)
            word_list = self.chain_dict.get(combined, ".")
            if word_list != ".":
                if len(word_list) > 1:
                    word = self.get_word(word_list)
                else:
                    word = word_list.items()[0][0]
                    output = "{} {}".format(output, word)
            else:
                word = "."
                output = "{}{}".format(output.strip(), word)
            pre1, pre2 = pre2, word
            if word == ".":
                sent_count += 1

        return output

    def get_word(self, possibilities=None):
        word_list = []
        for word in possibilities:
            word_list.extend([word] * possibilities[word])
        return random.choice(word_list)


def learn_user(nick, content):
    user = USERS.get(DB_Q.nick == nick)
    if not user:
        new_mkdb = MarkovChain()
        USERS.insert({'nick': nick, 'mkdb': new_mkdb})
        user = USERS.get(DB_Q.nick == nick)
    user['mkdb'].learn(content)
    USERS.update(user, eids=[user.eid])


@hook.on_start()
def load_db(bot, conn):
    """Load in our database and create our query object"""
    global CACHE, USERS, DB_Q
    CACHE = TinyDB('mock.json')
    USERS = CACHE.table('users')
    DB_Q = Query()


@hook.event([EventType.message, EventType.action])
def listen(event):
    learn_user('!chan!', event.content)
    learn_user(event.nick, event.content)


@hook.command('mock')
def mock(text):
    if not text:
        text = '!chan!'
    user = USERS.get(DB_Q.nick == text)
    if not user:
        return 'The user {} was not found in my databse.'.format(text)
    return user['mkdb'].gen_text()
