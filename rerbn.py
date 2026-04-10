
from datetime import datetime
import logging
import os
import aiohttp

log = logging.getLogger("discord")

rerbn_callgroup = os.environ.get('RERBN_CALLGROUP', None)
callgroup_editkey = os.environ.get('RERBN_CALLGROUP_EDITKEY', None)


async def query_rerbn(session: aiohttp.ClientSession):
    '''
    Get the spots from a Vail's ReRBN API by using a named Callsign group.

    This group should be created outside of the bot b/c the edit key the ReRBN
    returns from API is needed for future management of callsign list.
    '''

    callgroup = rerbn_callgroup

    if callgroup is None:
        log.warning("No callgroup name is configured to query ReRBN. skipping")
        return []

    url = f'https://vailrerbn.com/api/v1/groups/{callgroup}/spots?mode=CW'

    async with session.get(url) as response:
        if response.status == 200:
            j = await response.json()

            # sort by id asc. last assignment to dict entry will be latest
            a = j.get('spots', {})
            sorted_list = sorted(a, key=lambda x: x['id'])

            spots = {}

            for spot in sorted_list:
                converted = convert_rerbn_to_pota_spot(spot)
                spots[spot['callsign']] = converted

            return list(spots.values())


def convert_rerbn_to_pota_spot(spot):
    iso_8601 = spot["timestamp"]
    # remove Z and add UTC offset
    t = datetime.fromisoformat(iso_8601.replace('Z', '+00:00'))
    timestamp = t.isoformat()
    snr = spot["snr"]
    wpm = spot["wpm"]
    return {
        'activator': spot["callsign"],
        'frequency': spot["frequency"],
        'mode': 'CW',         # URL only gets CW spots
        'spotTime': timestamp,
        'comments': '##RBN##',  # hijack comment field for flag
        'reference': f'de {spot["spotter"]} at {spot["spotter_grid"]}',
        'name': f'{snr} db • {wpm} wpm',
        'locationDesc': ''
    }


async def add_call_to_callgroup(
        session: aiohttp.ClientSession,
        callsign: str) -> tuple[bool, str]:
    if callgroup_editkey is None or rerbn_callgroup is None:
        msg = "No editkey or callgroup configured. skipping rerbn callgroup."
        log.info(msg)
        return (True, msg)

    data = {
        "add_callsigns": [callsign],
        "description": "73 de spotbot"
    }

    url = f"https://vailrerbn.com/api/v1/groups/{rerbn_callgroup}?edit_key={callgroup_editkey}"

    log.info(f"ReRBN addcall url: {url}")
    async with session.put(url, json=data) as response:
        log.info(f"RERBN api returned: {response}")
        if response.status == 200:
            return (True, None)
        else:
            return (False, f"Error from API {response.status}")


async def remove_call_from_callgroup(
        session: aiohttp.ClientSession,
        callsign: str) -> tuple[bool, str]:
    if callgroup_editkey is None or rerbn_callgroup is None:
        msg = "No editkey or callgroup configured. skipping rerbn callgroup."
        log.info(msg)
        return (True, msg)

    data = {
        "remove_callsigns": [callsign],
        "description": "73 de spotbot"
    }

    url = f"https://vailrerbn.com/api/v1/groups/{rerbn_callgroup}?edit_key={callgroup_editkey}"

    log.info(f"ReRBN remove call url: {url}")
    async with session.put(url, json=data) as response:
        log.info(f"RERBN api returned: {response}")
        if response.status == 200:
            return (True, None)
        else:
            return (False, f"Error from API {response.status}")
