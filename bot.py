# noqa E501

from datetime import datetime, timezone, timedelta
import os
import requests
import discord
from discord.ext import tasks
from discord import app_commands
import logging
import logging.handlers


POTA_SPOT_URL = "https://api.pota.app/spot/activator"
ACTIVATOR_INFO_URL = "https://api.pota.app/stats/user/{call}"

token = os.environ['BOT_TOKEN']
guild_id = int(os.environ['GUILD_ID'])
channel_id = int(os.environ['CHANNEL_ID'])
callsign_role_id = int(os.environ['CALLSIGN_MGR_ROLE_ID'])
ping_role = int(os.environ['PING_ROLE_ID'])

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
                "url": "https://gravatar.com/avatar/f956ca7887ccc87645abc313a4a3a373?d=identicon"
            }
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


def get_spots():
    '''Return all current spots from POTA API'''
    response = requests.get(POTA_SPOT_URL)
    if response.status_code == 200:
        j = response.json()
        return j


def get_activator_stats(activator: str):
    '''Return all spot + comments from a given activation'''
    s = get_basecall(activator)

    url = ACTIVATOR_INFO_URL.format(call=s)
    response = requests.get(url)
    if response.status_code == 200:
        j = response.json()
        return j
    else:
        return None


def get_callsign_list() -> list[str]:
    with open(file="callsigns.txt", mode="r") as f:
        lines = f.readlines()

    return [s.strip() for s in lines]


def add_callsign(callsign: str):
    calls = get_callsign_list()
    if callsign in calls:
        return
    calls.append(callsign)
    with open(file="callsigns.txt", mode="w") as f:
        f.write('\n'.join(calls))


def remove_callsign(callsign: str):
    calls = get_callsign_list()
    if callsign not in calls:
        return
    calls.remove(callsign)
    with open(file="callsigns.txt", mode="w") as f:
        f.write('\n'.join(calls))


def build_embed(spot: any) -> str:
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
        act_url = f"https://pota.app/#/profile/{call}"
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

    act_info = get_activator_stats(act)
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


class Storage:
    def __init__(self):
        self.spots = []

    def add_spot(self, spot: any):
        x = {
            'timestamp': datetime.now(timezone.utc),
            'spot': spot,
            'qrt': False
        }
        self.spots.append(x)

    def check_spot(self, spot: any):
        new_act = spot['activator']
        new_freq = spot['frequency']
        new_mode = str(spot['mode'])
        new_time = datetime.fromisoformat(spot['spotTime'])
        new_time = datetime(new_time.year, new_time.month, new_time.day, new_time.hour,
                            new_time.minute, new_time.second, new_time.microsecond, timezone.utc)

        for s in self.spots:
            act = s['spot']['activator']
            old_freq = s['spot']['frequency']
            old_mode = s['spot']['mode']
            if act == new_act:
                if old_freq != new_freq and not new_mode.startswith('FT'):
                    self.spots.remove(s)
                    self.add_spot(spot)
                    return True
                if old_mode != new_mode:
                    self.spots.remove(s)
                    self.add_spot(spot)
                    return True

                cmt = str(spot['comments'])
                if "qrt" in cmt.lower():
                    if s['qrt']:
                        # QRT msg has already been sent
                        return False
                    else:
                        s['qrt'] = True
                        return True
                return False

            # remove any old spots we have
            now = datetime.now(timezone.utc)
            if now - s['timestamp'] > timedelta(minutes=30):
                self.spots.remove(s)

        self.add_spot(spot)
        return True


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

    async def on_ready(self):
        log.info(f'onready: Logged in as {self.user} (ID: {self.user.id})')

    @tasks.loop(seconds=30)
    async def my_background_task(self):
        channel = self.get_channel(channel_id)

        calls = get_callsign_list()
        spots = get_spots()

        for spot in spots:
            act = spot['activator']
            act = get_basecall(act)

            if act in calls:
                must_send = self.storage.check_spot(spot)

                if must_send:
                    msg = build_embed(spot)
                    embed = discord.Embed.from_dict(msg['embeds'][0])
                    await channel.send(
                        content=f'<@&{ping_role}> POTA SPOT',
                        embed=embed)

    @my_background_task.before_loop
    async def before_my_task(self):
        # wait until the bot logs in
        await self.wait_until_ready()


mentions = discord.AllowedMentions(roles=True, users=True, everyone=False)


client = MgraBot(
    intents=discord.Intents.default(),
    allowed_mentions=mentions)


@client.tree.command(
    name="showcalls",
    description="Show the list of skimmed callsigns",
    guild=discord.Object(id=guild_id)
)
async def show_calls_cmd(interaction):
    t = get_callsign_list()
    msg = ",".join(t)
    await interaction.response.send_message(f"### Configured callsigns \n{msg}", ephemeral=True)


@client.tree.command(
    name="addcall",
    description="Add a callsign to the list of skimmed callsigns. Don't add '/' suffixes or prefixes",
    guild=discord.Object(id=guild_id),
)
@app_commands.describe(callsign='The callsign to add to the tracking list.')
@app_commands.checks.has_role(callsign_role_id)
async def add_call_cmd(interaction: discord.Interaction, callsign: str):
    log.info(f"adding callsign {callsign}. user: {interaction.user} - {interaction.user.id}")
    add_callsign(callsign.upper())
    await interaction.response.send_message(f"### Callsign added\n {callsign}", ephemeral=True)


@add_call_cmd.error
async def add_call_cmd_error(interaction: discord.Interaction, error):
    await interaction.response.send_message(f"Error: _{error}_", ephemeral=True)


@client.tree.command(
    name="removecall",
    description="Remove a callsign to the list of skimmed callsigns",
    guild=discord.Object(id=guild_id)
)
@app_commands.describe(callsign='The callsign to remove from the tracking list')
@app_commands.checks.has_role(callsign_role_id)
async def remove_call_cmd(interaction: discord.Interaction, callsign: str):
    log.info(f"removing callsign {callsign}. user: {interaction.user} - {interaction.user.id}")
    remove_callsign(callsign.upper())
    await interaction.response.send_message(f"### Callsign removed\n {callsign}", ephemeral=True)


@remove_call_cmd.error
async def remove_call_cmd_error(interaction: discord.Interaction, error):
    await interaction.response.send_message(f"Error: _{error}_", ephemeral=True)


client.run(token, log_handler=handler)
