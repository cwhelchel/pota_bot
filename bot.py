# noqa E501

import asyncio
import json
import logging
import logging.handlers
import os
import re
import urllib.parse
from datetime import datetime, timezone, timedelta

import aiohttp
import discord
from cache import AsyncTTL
from discord.ext import tasks
from discord import app_commands

mutex_lock = asyncio.Lock()

POTA_SPOT_URL = "https://api.pota.app/spot/activator"
ACTIVATOR_INFO_URL = "https://api.pota.app/stats/user/{call}"

token = os.environ['BOT_TOKEN']
guild_id = int(os.environ['GUILD_ID'])
channel_id = int(os.environ['CHANNEL_ID'])
callsign_role_id = int(os.environ['CALLSIGN_MGR_ROLE_ID'])
ping_role = int(os.environ['PING_ROLE_ID'])
# default disable_rbn to FALSE
disable_rbn = int(os.environ.get('DISABLE_RBN', '0'))

handler = logging.handlers.RotatingFileHandler(
    filename='discord.log',
    encoding='utf-8',
    maxBytes=32 * 1024 * 1024,  # 32 MiB
    backupCount=5,  # Rotate through 5 files
)
log = logging.getLogger("discord")

test_msg = {
    "content": "",
    "tts": False,
    "embeds": [
        {
            "title": "N7OOS - - - *US-11254*  - - -  (SSB on 14285 MHz)",
            "description": "2024-01-01 14:50 • park • profile • qrz",
            "color": 2326507,
            "fields": [
                {
                    "name": "Activator",
                    "value": "Jim Vaughn"
                },
                {
                    "name": "Location",
                    "value": "US-FL",
                    "inline": False
                },
                {
                    "name": "Comments",
                    "value": "",
                    "inline": False
                }
            ],
            "thumbnail": {
                "url": ""
            }
        }
    ],
    "components": [],
    "actions": {},
    "username": "MGRA Bot"
}

rbn_msg = {
    "content": "",
    "tts": False,
    "embeds": [
        {
            "title": "",
            "description": "",
            "color": 8383267,
            "fields": [
                {
                    "name": "Type",
                    "value": "RBN"
                },
                {
                    "name": "Spotted By",
                    "value": ""
                },
            ],
        }
    ],
    "components": [],
    "actions": {},
    "username": "MGRA Bot"
}


def get_basecall(callsign: str) -> str:
    '''
    Get the base component of a given callsign (ie. the callsign without '/P'
    suffixes or country prefixes ie 'W4/').
    '''
    if callsign is None:
        return ""

    if "/" in callsign:
        basecall = max(
            callsign.split("/")[0],
            callsign.split("/")[1],
            key=len)
    else:
        basecall = callsign
    return basecall


def validate_call(callsign: str) -> bool:
    '''
    Validates a callsign.

    The format should be pretty normal US amateur radio callsign.
    '''
    base = get_basecall(callsign)
    pattern = r'\d?[a-zA-Z]{1,2}\d{1,4}[a-zA-Z]{1,4}'
    m = re.match(pattern, base)

    if m:
        return True
    return False


async def get_spots(session):
    '''Return all current spots from POTA API'''
    async with session.get(POTA_SPOT_URL) as response:
        if response.status == 200:
            return await response.json()
        else:
            return []


async def get_rbn_spots(session, calls: list[str]):
    '''Return RBN spots for each callsign in the given list'''
    x = []
    for call in calls:
        x.append(query_rbn(session, call))

    return await asyncio.gather(*x)


def convert_rbn_to_pota_spot(j, spot):
    arr = j['spots'][spot]
    t = datetime.fromtimestamp(arr[11], tz=timezone.utc)
    timestamp = t.isoformat()
    snr = arr[3]
    wpm = arr[4]
    return {
        'activator': arr[2],
        'frequency': arr[1],
        'mode': 'CW',         # URL only gets CW spots
        'spotTime': timestamp,
        'comments': '##RBN##',  # hijack comment field for flag
        'reference': f'de {arr[0]}',
        'name': f'{snr} db • {wpm} wpm',
        'locationDesc': ''
    }


async def query_rbn(session, call: str):

    # h = returned as "ver_h": "4f6ae8" (version header maybe?)
    # ma = max age in seconds
    # m = 1 (CW)
    # bc = 1 (CQ)
    # s = 0 ???
    # r = max rows (100 is highest)
    # cdx = callsign to look for
    call = urllib.parse.quote(call)
    url = f'https://www.reversebeacon.net/spots.php?h=4f6ae8&ma=60&m=1&bc=1&s=0&r=100&cdx={call}'

    async with session.get(url) as response:
        if response.status == 200:
            j = await response.json()

            for spot in j.get('spots', []):
                # Just return first match
                return convert_rbn_to_pota_spot(j, spot)


@AsyncTTL(time_to_live=6 * 60 * 60, skip_args=1)  # 6hours
async def get_activator_stats(session, activator: str):
    '''Return all spot + comments from a given activation'''
    s = get_basecall(activator)

    url = ACTIVATOR_INFO_URL.format(call=s)
    async with session.get(url) as response:
        if response.status == 200:
            return await response.json()
        else:
            return None


async def get_callsign_list() -> list[str]:
    async with mutex_lock:
        return _get_callsign_list()


def _get_callsign_list() -> list[str]:
    with open(file="callsigns.txt", mode="r") as f:
        lines = f.readlines()

    return [s.strip() for s in lines]


async def add_callsign(callsign: str):
    async with mutex_lock:
        calls = _get_callsign_list()
        if callsign in calls:
            return
        if not validate_call(callsign):
            log.error("callsign is not valid")
            raise ValueError("callsign is not valid")

        calls.append(callsign)
        with open(file="callsigns.txt", mode="w") as f:
            f.write('\n'.join(calls))


async def remove_callsign(callsign: str):
    async with mutex_lock:
        calls = _get_callsign_list()
        if callsign not in calls:
            return
        calls.remove(callsign)
        with open(file="callsigns.txt", mode="w") as f:
            f.write('\n'.join(calls))


async def build_pota_embed(session, spot: any) -> str:
    '''
    The bulk of the work is done here to format spot data into a nice looking
    discord embed

    @param spot any: a spot from the pota api
    '''
    def get_title(act, ref, mode, freq):
        return f"{act} — *{reference}*  —  {freq} ({mode})"

    def get_act_title(name, actx, qsos):
        return f"_{name}_   ( **{actx}** actx / **{qsos}** qs )"

    def get_gravatar(id):
        return f"https://gravatar.com/avatar/{id}?d=identicon"

    def get_description(ref, call, timestamp):
        park_url = f"https://pota.app/#/park/{ref}"
        act_url = f"https://pota.app/#/profile/{get_basecall(call)}"
        qrz_url = f"https://www.qrz.com/db/{call}"
        return f"{timestamp} • [park]({park_url}) • [profile]({act_url}) • [qrz]({qrz_url})"

    act = spot['activator']
    freq = spot['frequency']
    mode = spot['mode']
    reference = spot['reference']
    park_name = spot['name']
    locations = spot['locationDesc']
    timestamp = spot['spotTime']

    test_msg["embeds"][0]['title'] = get_title(act, reference, mode, freq)
    test_msg["embeds"][0]['description'] = get_description(reference, act, timestamp)

    act_info = await get_activator_stats(session, act)
    act_info_unknown = {
        "callsign": "unknown",
        "name": "unknown",
        "qth": "unknown",
        "gravatar": "",
        "activator": {
            "activations": '?',
            "parks": '?',
            "qsos": '?'
        },
        "attempts": {
            "activations": '?',
            "parks": '?',
            "qsos": '?'
        },
        "hunter": {
            "parks": '?',
            "qsos": '?'
        },
        "awards": '?',
        "endorsements": '?'
    }
    if act_info is None:
        act_info = act_info_unknown

    actx = act_info['activator']['activations']
    qsos = act_info['activator']['qsos']
    name = act_info['name']
    gravatar_id = act_info['gravatar']
    test_msg["embeds"][0]['thumbnail']['url'] = get_gravatar(gravatar_id)

    test_msg["embeds"][0]['fields'][0]['value'] = get_act_title(
        name, actx, qsos)
    test_msg["embeds"][0]['fields'][1]['value'] = f"{park_name}\n{locations}"
    test_msg["embeds"][0]['fields'][2]['value'] = spot['comments']

    return test_msg


def build_rbn_embed(spot: any) -> str:
    '''
    The bulk of the work is done here to format spot data into a nice looking
    discord embed

    @param spot any: a spot from the pota api
    '''
    def get_title(act, mode, freq):
        return f"{act} —  {freq} ({mode})"

    def get_description(call, timestamp):
        rbn_url = f"https://www.reversebeacon.net/main.php?spotted_call={call}"
        qrz_url = f"https://www.qrz.com/db/{call}"
        return f"{timestamp} • [rbn]({rbn_url}) • [qrz]({qrz_url})\n"

    act = spot['activator']
    freq = spot['frequency']
    mode = spot['mode']
    timestamp = spot['spotTime']

    rbn_msg["embeds"][0]['title'] = get_title(act, mode, freq)
    rbn_msg["embeds"][0]['description'] = get_description(act, timestamp)

    # reference is 'spotted by X' for RBN
    spotby = spot['reference'] + ' • ' + spot['name']
    rbn_msg["embeds"][0]['fields'][1]['value'] = spotby

    return rbn_msg


class Storage:
    def __init__(self):
        self.schedule = None
        self.spots = {}

    def add_spot(self, spot: any):
        self.spots[spot['activator']] = {
            'timestamp': datetime.now(timezone.utc),
            'spot': spot,
            'qrt': False
        }

    def check_freq(self, a: float, b: float):
        try:
            x = float(a)
            y = float(b)

            return (abs(x - y) >= 0.2)
        except Exception as e:
            print(f"error comparing frequency: {e}")
            log.error("error comparing frequency", exc_info=1)
            return False

    def check_spot(self, spot: any):
        act = spot['activator']
        cmt = str(spot['comments'])
        new_time = datetime.fromisoformat(spot['spotTime']).replace(tzinfo=timezone.utc)

        # if for some reason this spot is super old we dont want to process it
        # at all. assume it's in the list by mistake.
        #   (RBN started ignoring max age for ex)
        if (datetime.now(timezone.utc) - new_time) > timedelta(minutes=31):
            return False

        old_spot = self.spots.get(act)
        if old_spot is None:
            if "qrt" not in cmt.lower():
                self.add_spot(spot)
                return True
        else:
            old_freq = old_spot['spot']['frequency']
            old_mode = old_spot['spot']['mode']
            new_freq = spot['frequency']
            new_mode = str(spot['mode'])

            freq_changed = self.check_freq(old_freq, new_freq)

            if freq_changed and not new_mode.startswith('FT'):
                self.add_spot(spot)
                return True
            elif old_mode != new_mode:
                self.add_spot(spot)
                return True
            elif "qrt" in cmt.lower() and not old_spot['qrt']:
                old_spot['qrt'] = True
                return True
        return False

    def expire(self):
        # remove any old spots we have
        now = datetime.now(timezone.utc)
        for act in list(self.spots.keys()):
            if now - self.spots[act]['timestamp'] > timedelta(minutes=30):
                del self.spots[act]

    def get_schedule(self) -> any:
        try:
            with open(file="schedule.json", mode="r", encoding='utf8') as f:
                lines = f.read()
                self.schedule = json.loads(lines)
        except Exception as ex:
            print(f"Error getting schedule file: {ex}")
            log.error("Error getting schedule file", exc_info=ex)
            self.schedule = None

        return self.schedule


class MgraBot(discord.Client):
    '''
    The MGRA Discord bot object
    '''

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.storage = Storage()
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        synced = await self.tree.sync(guild=discord.Object(id=guild_id))
        log.info(f"synced {synced}")
        # start the task to run in the background
        self.my_background_task.start()
        self.check_scheduled_msgs.start()

    async def on_ready(self):
        log.info(f'onready: Logged in as {self.user} (ID: {self.user.id})')

    @tasks.loop(seconds=60)
    async def my_background_task(self):
        channel = self.get_channel(channel_id)
        calls = await get_callsign_list()

        async with aiohttp.ClientSession() as session:
            pota_spots = get_spots(session)
            if not disable_rbn:
                rbn_spots = get_rbn_spots(session, calls)
                both_spots = await asyncio.gather(pota_spots, rbn_spots)
                spots = both_spots[0] + both_spots[1]
            else:
                spots = await pota_spots

            for spot in spots:
                if spot is None:
                    continue
                act = spot['activator']
                act = get_basecall(act)

                if act in calls:
                    must_send = self.storage.check_spot(spot)

                    if must_send:
                        if spot['comments'] == '##RBN##':
                            msg = build_rbn_embed(spot)
                            spot_type = 'RBN'
                        else:
                            msg = await build_pota_embed(session, spot)
                            spot_type = 'POTA'

                        embed = discord.Embed.from_dict(msg['embeds'][0])
                        await channel.send(
                            content=f'<@&{ping_role}> {spot_type} SPOT',
                            embed=embed)
        self.storage.expire()

    @my_background_task.before_loop
    async def before_my_task(self):
        # wait until the bot logs in
        await self.wait_until_ready()

    @tasks.loop(seconds=60)
    async def check_scheduled_msgs(self):
        '''
        This Background task executes every minute to check the time and see if
        there are scheduled messages to send. If so send the configured message.
        '''
        now = datetime.now(timezone.utc)
        weekday = now.date().weekday()
        schedule = self.storage.get_schedule()

        if schedule is None:
            return

        try:
            for x in schedule:
                if weekday == x['dow']:
                    msg_time = x['time_utc'].split(':')
                    if now.hour == int(msg_time[0]) and now.minute == int(msg_time[1]):
                        await self._send_scheduled_msg(x)
        except Exception as ex:
            log.error("Error sending scheduled msg", exc_info=ex)
            print(f"Error sending scheduled msg {ex}")

    @check_scheduled_msgs.before_loop
    async def before_check_scheduled_msgs(self):
        # wait until the bot logs in
        await self.wait_until_ready()

    async def _send_scheduled_msg(self, json):
        '''
        Sends the configured schedule message.

        Args:
            json: The JSON of the msg. straight from schedule.json
        '''
        if json is None:
            return

        # msg field could be a list of strings or a string
        msg_content = json['msg']
        if type(msg_content) is list:
            msg_content = "\n".join(msg_content)

        raw_embeds = json['embeds']
        embeds = []
        for em_raw in raw_embeds:
            embeds.append(discord.Embed.from_dict(em_raw))

        channel_id = int(json['channel'])
        channel = self.get_channel(channel_id)
        await channel.send(content=msg_content, embeds=embeds)


mentions = discord.AllowedMentions(roles=True, users=True, everyone=True)

client = MgraBot(
    intents=discord.Intents.default(),
    allowed_mentions=mentions)


###
# SHOW CALL COMMAND
###


@client.tree.command(
    name="showcalls",
    description="Show the list of skimmed callsigns",
    guild=discord.Object(id=guild_id)
)
async def show_calls_cmd(interaction):
    t = await get_callsign_list()
    msg = ",".join(t)
    await interaction.response.send_message(f"### Configured callsigns \n{msg}", ephemeral=True)


@show_calls_cmd.error
async def show_call_cmd_error(interaction: discord.Interaction, error):
    await interaction.response.send_message(f"Error: _{error}_", ephemeral=True)


###
# ADD CALL COMMAND
###


@client.tree.command(
    name="addcall",
    description="Add a callsign to the list of skimmed callsigns. Don't add '/' suffixes or prefixes",
    guild=discord.Object(id=guild_id),
)
@app_commands.describe(callsign='The callsign to add to the tracking list.')
@app_commands.checks.has_role(callsign_role_id)
async def add_call_cmd(interaction: discord.Interaction, callsign: str):
    log.info(f"adding callsign {callsign}. user: {interaction.user} - {interaction.user.id}")
    await add_callsign(callsign.upper())
    await interaction.response.send_message(f"### Callsign added\n {callsign}", ephemeral=True)


@add_call_cmd.error
async def add_call_cmd_error(interaction: discord.Interaction, error):
    await interaction.response.send_message(f"Error: _{error}_", ephemeral=True)


###
# REMOVE CALL COMMAND
###


@client.tree.command(
    name="removecall",
    description="Remove a callsign to the list of skimmed callsigns",
    guild=discord.Object(id=guild_id)
)
@app_commands.describe(callsign='The callsign to remove from the tracking list')
@app_commands.checks.has_role(callsign_role_id)
async def remove_call_cmd(interaction: discord.Interaction, callsign: str):
    log.info(f"removing callsign {callsign}. user: {interaction.user} - {interaction.user.id}")
    await remove_callsign(callsign.upper())
    await interaction.response.send_message(f"### Callsign removed\n {callsign}", ephemeral=True)


@remove_call_cmd.error
async def remove_call_cmd_error(interaction: discord.Interaction, error):
    await interaction.response.send_message(f"Error: _{error}_", ephemeral=True)


client.run(token, log_handler=handler)
