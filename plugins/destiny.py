import datetime
import tweepy
from cloudbot import hook
from cloudbot.util.web import try_shorten
from cloudbot.util import timeformat
from datetime import datetime
from feedparser import parse
from html.parser import HTMLParser
from pickle import dump, load
from plugins.twitter import load_api, twitter
from random import sample
from requests import get
from tinydb import TinyDB, Query

BASE_URL = 'https://www.bungie.net/platform/Destiny/'
CLASS_TYPES = {0: 'Titan ', 1: 'Hunter ', 2: 'Warlock ', 3: ''}
CLASS_HASH = {671679327: 'Hunter', 3655393761: 'Titan', 2271682572: 'Warlock'}
RACE_HASH = {898834093: 'Exo', 3887404748: 'Human', 2803282938: 'Awoken'}
CONSOLES = ['\x02\x033Xbox\x02\x03', '\x02\x0312Playstation\x02\x03']
STAT_HASHES = {144602215: 'Int', 1735777505: 'Disc', 4244567218: 'Str'}
ENEMY_RACE_HASH = {3265589059: 'Hive', 546070638: 'Cabal', 711470098: 'Vex', 1636291695: 'Fallen'}
BOSS_COMBATANT_HASH = {1: 'Pilot Servitor', 2: 'Val Aru\'un', 3: 'Wretched Knight', 4: 'Overmind Minotaur', 5: 'Seditious Mind', 6: 'Noru’usk, Servant of Oryx', 7: 'Keksis the Betrayed', 8: 'Sylok, the Defiled'}
LORE_CACHE = {}
HEADERS = {}
WEAPON_TYPES = ['Super', 'Melee', 'Grenade', 'AutoRifle', 'FusionRifle',
    'HandCannon', 'Machinegun', 'PulseRifle', 'RocketLauncher', 'ScoutRifle',
    'Shotgun', 'Sniper', 'Submachinegun', 'Relic', 'SideArm']
WEAPON_CLASSES = {"PrimaryWeapon": ['HandCannon', 'AutoRifle', 'PulseRifle',
                                    'ScoutRifle'],
                  "SpecialWeapon": ['FusionRifle', 'Shotgun', 'Sniper', 'SideArm'],
                  "HeavyWeapon": ['Machinegun', 'Submachinegun', 'RocketLauncher',
                                  'Relic'],
                  "Ability": ['Super', 'Melee', 'Grenade']}
PVP_OPTS = ['activitiesEntered', 'assists', 'avgKillDistance', 'deaths', 'kills', 'k/d',
    'bestSingleGameKills', 'bestSingleGameScore', 'bestWeapon', 'longestKillSpree',
    'secondsPlayed', 'longestSingleLife', 'orbsDropped', 'precisionKills',
    'precisionRate', 'suicides', 'winRate', 'zonesCaptured']
PVE_OPTS = ['activitiesEntered', 'activitiesCleared', 'avgKillDistance',
    'bestSingleGameKills', 'bestWeapon', 'longestKillSpree', 'deaths', 'kills', 'k/h',
    'secondsPlayed', 'longestSingleLife', 'orbsDropped', 'precisionKills',
    'precisionRate', 'suicides', 'winRate', 'publicEventsCompleted']

class MLStripper(HTMLParser):
    def __init__(self):
        self.reset()
        self.strict = False
        self.convert_charrefs= True
        self.fed = []
    def handle_data(self, d):
        self.fed.append(d)
    def get_data(self):
        return ''.join(self.fed)

def strip_tags(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data().replace('\n', '\t')

def get_user(user_name, console=None, cached=True):
    '''
    Takes in a username and returns a dictionary of all systems they are
    on as well as their associated id for that system, plus general information
    '''
    global LINKS, USERS

    user = USERS.get(DB_Q.nick == user_name)
    if user and cached:
        return {x: user[x] for x in user if x != 'nick'}  # don't return nick info
    else:
        platforms = LINKS.search(DB_Q.nick == user_name)
        platforms = {console: user_name} if not platforms else platforms
        user_info = {}
        for platform in platforms:
            if platform not in [1, 2]:
                continue
            gamertag = platforms[platform]
            try:
                # Get the Destiny membership ID
                membershipId = get('{}SearchDestinyPlayer/{}/{}/'.format(BASE_URL, platform, gamertag),
                    headers=HEADERS).json()['Response'][0]['membershipId']
                # Then get Destiny summary
                characterHash = get(
                    '{}{}/Account/{}/Summary/'
                    .format(BASE_URL, platform, membershipId),
                    headers=HEADERS).json()['Response']['data']
            except:
                return 'A user by the name {} was not found.'.format(gamertag)

            character_dict = {}
            for character in characterHash['characters']:
                character_dict[character['characterBase']['characterId']] = {
                    'level': character['characterLevel'],
                    'LL': character['characterBase']['powerLevel'],
                    'race': RACE_HASH[character['characterBase']['raceHash']],
                    'class': CLASS_HASH[character['characterBase']['classHash']]
                }
            user_dict = {
                'membershipId': membershipId,
                'clan': characterHash.get('clanName', 'None'),
                'characters': character_dict
            }
            user_info[platform] = user_dict

        user = USERS.get(DB_Q.nick == user_name)
        if user:
            USERS.update(user_info, eids=[user.eid])
        else:
            eid = USERS.insert({'nick': user_name})
            USERS.update(user_info, eids=[eid])
        return user_info if user_info else 'A user by the name {} was not found.'.format(user_name)

def prepare_lore_cache():
    '''
   Store the current lore in our database
   '''
    lore_base = get('{}/Vanguard/Grimoire/Definition/'.format(BASE_URL),
        headers=HEADERS).json()['Response']['themeCollection']

    global LORE, COLLECTIONS
    LORE.purge()
    COLLECTIONS.purge()
    grim_tally = 0
    fragments = {}
    for level1 in lore_base:
        if level1.get('themeId', '') == 'Enemies':
            for page in level1['pageCollection']:
                if page['pageId'] == 'BooksofSorrow':
                    for card in page['cardCollection']:
                        fragments[card['cardId']] = card['cardName']
        for level2 in level1.get('pageCollection', []):
            for card in level2.get('cardCollection', []):
                LORE.insert({
                    'cardName': card['cardName'],
                    'cardIntro': card.get('cardIntro', ''),
                    'cardDescription': card['cardDescription'],
                    'cardId': card['cardId']
                })
            for card in level2.get('cardBriefs', []):
                grim_tally += card.get('totalPoints', 0)
    COLLECTIONS.insert({'ghost_tally': 103})
    COLLECTIONS.insert({'grim_tally': grim_tally})
    COLLECTIONS.insert({'fragments': fragments})


def best_weapon(data):
    best = 0
    weapon = None
    for stat in data:
        if 'weaponKills' in stat:
            if data[stat]['basic']['value'] > best:
                best = data[stat]['basic']['value']
                weapon = stat
    return '{}: {} kills'.format(
        weapon[11:], round(best)) if best else 'You ain\'t got no best weapon!'

def get_weaponclass_total(data, weapon_class):
    # TODO: No Land Beyond, Universal Remote, Sleeper Simulant, etc.
    if weapon_class in WEAPON_CLASSES:
        weaponclass_kills = 0
        for primitive_stat in WEAPON_CLASSES[weapon_class]:
            raw_stat = "weaponKills{0}".format(primitive_stat)
            weaponclass_kills += data[raw_stat]['basic']['value']
        return weaponclass_kills
    else:
        return None

def get_stat(data, stat):
    if stat in WEAPON_TYPES:
        stat = 'weaponKills{}'.format(stat)
    if stat in data:
        return '\x02{}\x02: {}'.format(
            data[stat]['statId'], data[stat]['basic']['displayValue'])
    elif stat.endswith("Percentage"):
        orig_stat = stat[:-len("Percentage")]
        if orig_stat in WEAPON_TYPES:
            orig_stat = "weaponKills{0}".format(orig_stat)
            return '\x02{0}\x02: {1}%'.format(stat, round( (data[orig_stat]['basic']['value'] /
                                                            data['kills']['basic']['value']) * 100, 2))
        elif orig_stat in WEAPON_CLASSES:
            return '\x02{0}\x02: {1}%'.format(stat, round( (get_weaponclass_total(data, orig_stat) /
                                                            data['kills']['basic']['value']) * 100, 2))
        else:
            return "Invalid percentage stat request {0}".format(orig_stat)
    elif stat in WEAPON_CLASSES:
        return '\x02{0}\x02: {1}'.format(stat, get_weaponclass_total(data, stat))
    elif stat == 'k/d':
        return '\x02k/d\x02: {}'.format(round(
            data['kills']['basic']['value'] / data['deaths']['basic']['value'], 2))
    elif stat == 'k/h':
        return '\x02k/h\x02: {}'.format(round(data['kills']['basic']['value'] / (
            data['secondsPlayed']['basic']['value'] / 3600), 2))
    elif stat == 'd/h':
        return '\x02d/h\x02: {}'.format(round(data['deaths']['basic']['value'] / (
            data['secondsPlayed']['basic']['value'] / 3600), 2))
    elif stat == 'avgKillDistance':
        return '\x02avgKillDistance\x02: {}m'.format(round(
            data['totalKillDistance']['basic']['value'] / data['kills']['basic']['value'], 2))
    elif stat == 'winRate':
        return '\x02winRate\x02: {}'.format(round(data['activitiesWon']['basic']['value'] / (
            data['activitiesEntered']['basic']['value'] - data['activitiesWon']['basic']['value']), 2))
    elif stat == 'precisionRate':
        return '\x02precisionRate\x02: {}'.format(round(data['precisionKills']['basic']['value'] / (
            data['kills']['basic']['value'] - data['precisionKills']['basic']['value']), 2))
    elif stat == 'bestWeapon':
        return '\x02bestWeapon\x02: {}'.format(best_weapon(data))
    else:
        return 'Invalid option {}'.format(stat)

def in_lower(val, target):
    """Helper function for tinydb searches."""
    return target.lower() in val.lower()

@hook.periodic(300, initial_interval=300)
def check_updates(message, bot):
    """Check to see if there have been any updates from Bungie."""
    global CACHE
    twt1, twt2 = tweets(bot)
    fd = news(bot, chan=None)
    output = []
    updates = CACHE.get(DB_Q.updates.exists())
    if not updates:
        CACHE.insert({'updates': [twt1, twt2, fd]})
        output = [twt1, twt2, fd]
    else:
        if updates['updates'][0][50] != twt1[50]:
            updates['updates'][0] = twt1
            output.append(twt1)
        if updates['updates'][1][50] != twt2[50]:
            updates['updates'][1] = twt2
            output.append(twt2)
        if updates['updates'][2] != fd:
            updates['updates'][2] = fd
            output.append(fd)
        CACHE.update(updates, eids=[updates.eid])
    for conn in bot.connections:
        for chan in CACHE.get(DB_Q.channels.exists()).get('channels', None):
            for update in output:
                bot.connections[conn].message(chan, update)

@hook.on_start()
def load_db(bot, conn):
    """Load in our database and the Headers."""
    global CACHE, USERS, LORE, COLLECTIONS, LINKS, DB_Q, HEADERS
    CACHE = TinyDB('destiny.json')
    USERS = CACHE.table('users')
    LORE = CACHE.table('lore')
    COLLECTIONS = CACHE.table('collections')
    LINKS = CACHE.table('links')
    DB_Q = Query()  # This is our query object used. Use it in all queries.
    HEADERS = {'X-API-Key': bot.config.get('api_keys', {}).get('destiny', None)}


def compile_stats(text, nick, bot, opts, defaults, split_defaults, st_type, notice):
    if not text:
        text = nick
    text = text.split(' ')
    CONSOLE_MAP = {"xbox": 1, "playstation": 2}

    # Do you need help?
    if text[0].lower() == 'help':
        notice('options: {}'.format(', '.join(opts + WEAPON_TYPES)))
        return

    target = compile_stats_arg_parse(text, nick)

    if target['user'] is None or not target['nick']:
        return "No possible user found."

    membership = target['user']

    # if no stats are specified, add some
    if not target['stats']:
        target['stats'] = defaults if not target['split'] else split_defaults
    split = target['split']
    path = 'characters' if split else 'mergedAllCharacters'

    output = []
    for console in membership:
        # If a console has been specified, grab only that console
        if target['console'] and console != CONSOLE_MAP[target['console']]:
            continue

        # Get stats
        data = get(
            '{}Stats/Account/{}/{}/'.format(
                BASE_URL, console, membership[console]['membershipId']),
            headers=HEADERS
        ).json()['Response'][path]
        tmp_out = []
        if not split:
            try:
                data = data['results'][st_type]['allTime']
                for stat in target['stats']:
                    tmp_out.append(get_stat(data, stat))
            except KeyError:
                return "Data not available yet."
        else:
            for character in data:
                if not character['deleted'] and character['results'][st_type].get('allTime', False):
                    tmp_out.append('\x02{}\x02 {}'.format(
                        membership[console]['characters'][character['characterId']]['class'],
                        " / ".join([get_stat(character['results'][st_type]['allTime'], stat) for stat in target['stats']])
                    ))

        output.append('{}: {}'.format(CONSOLES[console - 1], ', '.join(tmp_out)))
    return '\x02{0}\x02: {1}'.format(target['nick'], '; '.join(output))

def compile_stats_arg_parse(text_arr, given_nick, cached=True):
    '''Parse the input

    :param textArr: the input text array to parse
    :type  textArr: string
    :param nick: the nick to get stats on
    :type nick: string

    :returns: a dictionary of values to use
    :rtype: dictionary of strings
    '''

    CONSOLES = {"xbl": "xbox", "psn": "playstation"}
    CONSOLE2ID = {"xbox": 1, "playstation": 2}
    nick = ''
    user = None
    console = None
    collect = []
    split = False

    # Nick/console
    args = text_arr[:]
    while args:
        check_arg = args.pop(0)
        if check_arg in CONSOLES and not console:
            console = CONSOLES[check_arg]
            if user:
                # better run it again
                user = get_user(nick, CONSOLE2ID[console], cached=cached)
            elif collect:
                # gamertag may have been given, try it
                for i, arg in enumerate(collect):
                    user = get_user(arg, CONSOLE2ID[console], cached=cached)
                    if not isinstance(user, str):
                        # Gamertag given, found, remove it.
                        collect.pop(i)
                        nick = arg
                        break
        elif check_arg == 'split':
            split = True
        elif not nick:
            if console:
                # perfect, we can just return the user for it
                t = get_user(check_arg, CONSOLE2ID[console], cached=cached)
            else:
                # not perfect, but give it a shot
                t = get_user(check_arg, cached=cached)

            if not isinstance(t, str):
                # XXX: Right now, the only string returned is "A user by
                # the name (nick) can't be found." So 'string' return
                # type means that's the case; anything else is real,
                # valid, good data.
                user = t
                nick = check_arg
            else:
                # not split, not nick, not console
                # must be collect
                collect.append(check_arg)
        else:
            collect.append(check_arg)

    # If we didn't get a nick, assume the requester.
    if not nick:
        user = get_user(given_nick, CONSOLE2ID[console], cached=cached) if console else get_user(given_nick, cached=cached)
        if not isinstance(user, str):
           nick = given_nick
        else:
           user = None

    return_dict = {'user': user, 'nick': nick, 'console': console, 'stats': collect, 'split': split}
    return return_dict


@hook.command('pvp')
def pvp(text, nick, bot, notice):
    defaults = ['k/d', 'k/h', 'd/h', 'kills', 'bestSingleGameKills',
        'longestKillSpree', 'bestWeapon', 'secondsPlayed']
    split_defaults = ['k/d']
    return compile_stats(
        text=text,
        nick=nick,
        bot=bot,
        opts=PVP_OPTS,
        defaults=defaults,
        split_defaults=split_defaults,
        st_type='allPvP',
        notice=notice
    )

@hook.command('pve')
def pve(text, nick, bot, notice):
    defaults = ['k/h', 'kills', 'activitiesCleared', 'longestKillSpree',
        'bestWeapon', 'secondsPlayed']
    split_defaults = ['k/d']
    return compile_stats(
        text=text,
        nick=nick,
        bot=bot,
        opts=PVE_OPTS,
        defaults=defaults,
        split_defaults=split_defaults,
        st_type='allPvE',
        notice=notice
    )


@hook.command('item')
def item_search(text, bot):
    '''
    Expects the tex to be a valid object in the Destiny database
    Returns the item's name and description.
    TODO: Implement error checking
    '''
    item = text.strip()
    itemquery = '{}Explorer/Items?name={}'.format(BASE_URL, item)
    itemHash = get(
        itemquery, headers=HEADERS).json()['Response']['data']['itemHashes']

    output = []
    for item in itemHash:
        itemquery = '{}Manifest/inventoryItem/{}'.format(BASE_URL, item)
        result = get(
            itemquery, headers=HEADERS).json()['Response']['data']['inventoryItem']

        output.append('\x02{}\x02 ({} {}{}) - \x1D{}\x1D - http://www.destinydb.com/items/{}'.format(
            result['itemName'],
            result['tierTypeName'],
            CLASS_TYPES[result['classType']],
            result['itemTypeName'],
            result.get('itemDescription', 'Item has no description.'),
            result['itemHash']
        ))
    return output[:3]


@hook.command('nightfall')
def nightfall(text, bot):
    global CACHE
    curr_nf = CACHE.get(DB_Q.nightfall.exists())
    last_nf = CACHE.get(DB_Q.last_nightfall.exists())
    if curr_nf and not text.lower() == 'flush':
        if 'last' in text.lower():
            return last_nf['last_nightfall'] or 'Unavailable'
        else:
            return curr_nf['nightfall']
    else:
        advisors = get(
            '{}advisors/?definitions=true'.format(BASE_URL),
            headers=HEADERS).json()#['Response']['data']['nightfall']
        nightfallId = advisors['Response']['data']['nightfall']['specificActivityHash']
        nightfallActivityBundleHashId = advisors['Response']['data']['nightfall']['activityBundleHash']


        nightfallDefinition = advisors['Response']['definitions']['activities'][str(nightfallId)]

        output = '\x02{}\x02 - \x1D{}\x1D \x02Modifiers:\x02 {}'.format(
            nightfallDefinition['activityName'],
            nightfallDefinition['activityDescription'],
            ', '.join([advisors['Response']['definitions']['activities'][str(nightfallActivityBundleHashId)]['skulls'][skullId]['displayName'] for skullId in advisors['Response']['data']['nightfall']['tiers'][0]['skullIndexes']])
        )
        if curr_nf:
            if curr_nf['nightfall'] != output:
                CACHE.remove(q.last_nightfall.exists())
                CACHE.insert({'last_nightfall': curr_nf['nightfall']})
            CACHE.update({'nightfall': output}, eids=[curr_nf.eid])
        else:
            CACHE.insert({'nightfall': output})
        return output

@hook.command('coe')
def coe(text,bot):
    global CACHE
    curr_coe = CACHE.get(DB_Q.coe.exists())
    if curr_coe and text.lower() not in ['flush', 'clear', 'purge']:
        if 'last' in text.lower():
            return CACHE.get(DB_Q.last_coe.exists()).get('last_coe', 'Unavailable')
        else:
            return curr_coe['coe']
    else:
        advisors = get('{}advisors/?definitions=true'.format(BASE_URL),headers=HEADERS).json()['Response']['data']
        for activity in advisors['activities']:
            if activity['display']['advisorTypeCategory'] == 'Challenge of the Elders':
                modifiers = []
                for skullCategory in activity['extended']['skullCategories']:
                    for skull in skullCategory['skulls']:
                        modifiers.append(skull['displayName'])
                output = '\x02Challenge of the Elders\x02 - \x02Rounds:\x02 {} || \x02Modifiers:\x02 {}'.format(
                    ' // '.join(BOSS_COMBATANT_HASH[round['bossCombatantHash']] for round in activity['activityTiers'][0]['extended']['rounds']),
                    ' // '.join(modifiers)
                    )
                if curr_coe and output != curr_coe['coe']:
                    CACHE.remove(DB_Q.last_coe.exists())
                    CACHE.insert({'last_coe': curr_coe['coe']})
                    CACHE.update({'coe': output}, eids=[curr_coe.eid])
                else:
                    CACHE.insert({'coe': output})
                return output

@hook.command('xur')
def xur(text, bot):
    global CACHE
    if 'last' in text.lower():
        # return the last xur if it exists. If not return 'Unavailable'
        return CACHE.get(DB_Q.last_xur.exists()).get('xur', 'Unavailable')

    # reset happens at 9am UTC, so subtract that to simplify the math
    now = datetime.datetime.utcnow() - datetime.timedelta(hours=9)

    # xur is available from friday's reset until sunday's reset, i.e. friday (4) and saturday (5)
    if now.weekday() not in [4, 5]:
        xursday_diff = 4 - now.weekday()
        if xursday_diff < -1: # if past saturday, bump to next week
            xursday_diff += 7

        xursday = (now + datetime.timedelta(days=xursday_diff)).replace(hour=0, minute=0, second=0, microsecond=0)
        time_to_xursday = xursday - now

        s = time_to_xursday.seconds
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)

        output = []

        if time_to_xursday.days > 0:
            output.append('{} days'.format(time_to_xursday.days))

        if h: output.append('{} hours'.format(h))
        if m: output.append('{} minutes'.format(m))
        if s: output.append('{} seconds'.format(s))

        return '\x02Xûr will return in\x02 {}'.format(', '.join(output))

    curr_xur = CACHE.get(DB_Q.xur.exists())
    if curr_xur and not text.lower() == 'flush':
        return curr_xur['xur']

    xurStock = get(
        '{}Advisors/Xur/?definitions=true'.format(BASE_URL),
        headers=HEADERS).json()['Response']

    items = [i['item'] for i in xurStock['data']['saleItemCategories'][2]['saleItems']]
    definitions = xurStock['definitions']['items']

    output = []
    for item in items:
        item_def = definitions[str(item['itemHash'])]
        stats = []
        for stat in item['stats']:
            if stat['statHash'] in STAT_HASHES and stat['value'] > 0:
                stats.append('{}: {}'.format(STAT_HASHES[stat['statHash']], stat['value']))
        output.append('{}{}'.format(
            item_def['itemName'] if 'Engram' not in item_def['itemName'] else item_def['itemTypeName'],
            ' ({})'.format(', '.join(stats)) if stats else ''
        ))
    output = ', '.join(output)

    if curr_xur:
        if output != curr_xur['xur']:
            CACHE.remove(DB_Q.last_xur.exists())
            CACHE.insert({'last_xur': curr_xur['xur']})
            CACHE.update({'xur': output}, eids=[curr_xur.eid])
    else:
        CACHE.insert({'xur': output})
    return output


@hook.command('lore')
def lore(bot, notice, text=''):
    global LORE
    if len(LORE) < 10 or text.lower() == 'flush':  # if we need to make a new cache
        prepare_lore_cache()
        text = ''
    complete = 'complete' in text
    if complete:
        text = text.replace('complete', '').strip()

    if not text:  # if we aren't searching, return a random card
        card = sample(LORE.search(~DB_Q.cardName == 'grim_tally', 1))[0]
    else:
        matches = []
        card = LORE.get(DB_Q.cardName.search(text))
        if not card:
            matches.extend(LORE.search(
                DB_Q.cardName.test(in_lower, text) |
                DB_Q.cardIntro.test(in_lower, text) |
                DB_Q.cardDescription.test(in_lower, text)))
            if len(matches) == 1:
                card = matches[0]
            elif len(matches) == 0:
                return 'I ain\'t found shit!'
            elif complete:
                notice('I found {} matches. You can choose from:'.format(len(matches)))
                for line in matches:
                    notice(line['cardName'])
                return
            else:
                return ('I found {} matches, please be more specific '
                        '(e.g. {}). For a complete list use \'complete\''.format(
                            len(matches), ', '.join(
                                [match['cardName'] for match in matches[:3]])))

    output = strip_tags('{}: {} - {}'.format(
        card['cardName'], card.get('cardIntro', ''), card.get('cardDescription', '')))

    if complete:
        notice(output)
        return
    elif len(output) > 300:
        output = '{}... Read more at http://www.destinydb.com/grimoire/{}'.format(
            output[:301], contents['cardId'])

    return output if len(output) > 5 else lore('', bot, notice)

@hook.command('collection')
def collection(text, nick, bot):
    global LINKS
    text = nick if not text else text
    membership = get_user(text)
    links = LINKS.get(DB_Q.nick == text)

    if type(membership) == str:
        return membership

    output = []

    for console in membership:
        grimoire = get(
            '{}Vanguard/Grimoire/{}/{}/'
            .format(BASE_URL, console, membership[console]['membershipId']),
            headers=HEADERS
        ).json()['Response']['data']
        found_frags = []
        ghosts = 0
        fragments = COLLECTIONS.get(DB_Q.fragments.exists())['fragments']
        if not fragments:
            prepare_lore_cache()
            fragments = COLLECTIONS.get(DB_Q.fragments.exists())['fragments']
        for card in grimoire['cardCollection']:
            if card['cardId'] in fragments:
                found_frags.append([card['cardId']])
            elif card['cardId'] == 103094:
                ghosts = card['statisticCollection'][0]['displayValue']
                if int(ghosts) >= 99:
                    ghosts = 99

        if console == 1:
            platform = "xbl"
        else:
            platform = "psn"

        output.append('{}: Grimoire {}/{}, Ghosts {}/{}, Fragments {}/{} - {}'.format(
            CONSOLES[console - 1],
            grimoire['score'],
            COLLECTIONS.get(DB_Q.grim_tally.exists())['grim_tally'],
            ghosts,
            COLLECTIONS.get(DB_Q.ghost_tally.exists())['ghost_tally'],
            len(found_frags),
            len(fragments),
            try_shorten('http://destinystatus.com/{}/{}/grimoire'.format(
                platform,
                links[console]
            ))
        ))
    return output

@hook.command('link')
def link(text, nick, bot, notice):
    global LINKS
    text = text.lower().split(' ')
    err_msg = 'Invalid use of link command. Use: !link <gamertag> <xbl/psn>'

    # Check for right number of args
    if not 0 < len(text) < 3 or text[0] == '':
        notice(err_msg)
        return

    # Check that single arg is correct
    if len(text) == 1 and text[0] != 'flush':
        notice(err_msg)
        return

    # Clear all links if we need to flush
    if 'flush' in text:
        LINKS.remove(DB_Q.nick == nick)
        return '{} flushed from my cache'.format(nick)

    platform = text[1]
    gamertag = text[0]
    current = LINKS.get(DB_Q.nick == nick)
    if not current:
        LINKS.insert({'nick': nick})
        current = LINKS.get(DB_Q.nick == nick)
    if platform not in ['psn', 'xbl']:  # Check for a valid platform
        notice(err_msg)
        return
    elif platform == 'psn':
        current[2] = gamertag
        LINKS.update(current, eids=[current.eid])
        return '{} linked to {} on Playstation'.format(gamertag, nick)
    elif platform == 'xbl':
        current[1] = gamertag
        LINKS.update(current, eids=[current.eid])
        return '{} linked to {} on Xbox'.format(gamertag, nick)
    else:
        notice(err_msg)
        return

@hook.command('migrate')
def migrate(text, nick, bot):
    global LINKS
    if nick in ['weylin', 'avcables', 'DoctorRaptorMD[XB1]', 'tuzonghua']:
        global CACHE
        from pickle import load
        try:
            with open('destiny_cache', 'rb') as f:
                old_cache = load(f)  # load this old crap!
                for old_link in old_cache['links']:
                    if not LINKS.get(DB_Q.nick == old_link):
                        eid = LINKS.insert({'nick': old_link})
                        LINKS.update(old_cache['links'][old_link], eids=[eid])
            return 'Sucessfully migrated!'
        except:
            return "Couldn't load the old cache. Make sure 'destiny_cache' exists."

    else:
        return 'Your light is not strong enough.'

@hook.command('purge')
def purge(text, nick, bot):
    global USERS
    membership = get_user(nick)

    if type(membership) is not dict:
        return membership
    output = []
    text = '' if not text else text
    user = USERS.get(DB_Q.nick == nick)
    if text.lower() == 'xbl' and membership.get(1, False):
        del membership[1]
        output.append('Removed Xbox from my cache on {}.'.format(nick))
    if text.lower() == 'psn' and membership.get(2, False):
        del membership[2]
        output.append('Removed Playstation from my cache on {}.'.format(nick))
    if not text or not membership:
        USERS.remove(DB_Q.nick == nick)
        return 'Removed {}\'s characters from my cache.'.format(nick)
    else:
        USERS.update({nick: membership}, eids=[user.eid])
        return output if output else 'Nothing to purge. WTF you doin?!'

@hook.command('profile')
def profile(text, nick, bot):
    text = nick if not text else text
    membership = get_user(text)
    if type(membership) is not dict:
        return membership

    if membership.get(1, False):
        platform = 1
        membershipId = membership.get(1)['membershipId']
    elif membership.get(2, False):
        platform = 2
        membershipId = membership.get(2)['membershipId']
    else:
        return 'No profile!'

    bungieUserId = get(
        'http://www.bungie.net/Platform/User/GetBungieAccount/{}/{}/'.format(membershipId, platform),
        headers=HEADERS).json()['Response']['bungieNetUser']['membershipId']

    return 'https://www.bungie.net/en/Profile/254/{}'.format(bungieUserId)

@hook.command('chars')
def chars(text, nick, bot, notice):
    text = nick if not text else text
    text = text.split(' ')
    CONSOLE2ID = {"xbox": 1, "playstation": 2}

    err_msg = 'Invalid use of chars command. Use: !chars <nick> or !chars <gamertag> <psn/xbl>'

    target = compile_stats_arg_parse(text, nick, cached=False)
    if target['stats'] or target['split']:
        return err_msg

    characterHash = target['user']

    if type(characterHash) is not dict:
        return 'A user by the name {} was not found.'.format(text[0])

    output = []
    for console in characterHash:
        if target['console'] and CONSOLE2ID[target['console']] != console:
            print("{0} is not {1}".format(console, target['console']))
            continue
        console_output = []
        for char in characterHash[console]['characters']:
            console_output.append('✦{} // {} // {} - {}'.format(
                characterHash[console]['characters'][char]['LL'],
                characterHash[console]['characters'][char]['class'],
                characterHash[console]['characters'][char]['race'],
                try_shorten('https://www.bungie.net/en/Legend/Gear/{}/{}/{}'.format(
                    console,
                    characterHash[console]['membershipId'],
                    char
                ))
            ))
        output.append('{}: {}'.format(
            CONSOLES[console - 1],
            ' || '.join(console_output)
        ))
    return "\x02{0}\x02: {1}".format(target['nick'], ' ; '.join(output))

@hook.command('rules')
def rules(bot):
    return 'Check \'em! https://www.reddit.com/r/DestinyTheGame/wiki/irc'

@hook.command('compare')
def compare(text, bot):
    return 'Do it your fucking self, lazy bastard!'

@hook.command('ping')
def ping(text, bot):
    return 'pong'

@hook.command('ooboo')
def ooboo(text, bot):
    return 'https://www.youtube.com/watch?v=HJKW2ZcRtMY'

@hook.command('100')
def the100(bot):
    return 'Check out our The100.io group here: https://www.the100.io/g/1151'

@hook.command('clan')
def clan(bot):
    return 'Check out our Clan: https://www.bungie.net/en/Clan/Detail/939927'

@hook.command('news')
def news(bot, chan, text=None):
    global CACHE
    if text:
        channels = CACHE.get(DB_Q.channels.exists())
        if 'unsubscribe' in text.lower():
            if channels:
                if chan in channels['channels']:
                    channels['channels'].remove(chan)
                    CACHE.update(channels, eids=[channels.eid])
                    return 'Successfully unsubscribed!'
        elif 'subscribe' in text.lower():
            if not channels:
                CACHE.insert({'channels': [chan]})
            elif chan not in channels['channels']:
                channels['channels'].append(chan)
                CACHE.update(channels, eids=[channels.eid])
                return 'Successfully subscribed!'

    feed = parse('https://www.bungie.net/en/Rss/NewsByCategory?category=destiny&currentpage=1&itemsPerPage=1')
    if not feed.entries:
        return 'Feed not found.'

    return '{} - {}'.format(
        feed['entries'][0]['summary'],
        try_shorten(feed['entries'][0]['link']))

@hook.command('tweets')
def tweets(bot):
    load_api(bot)
    bungie = twitter("bungie 1")
    bungiehelp = twitter("bungiehelp 1")
    return (bungie, bungiehelp)
