
from datetime import datetime, timezone
import json
import logging
import os
import aiohttp
import urllib.parse

log = logging.getLogger("discord")


# this isn't really needed, but if someone sets RBN_HDR in their environment
# then we just use that and never pull latest header ver before getting spots
rbn_api_hdr = os.environ.get('RBN_HDR', None)


async def get_rbn_header(session: aiohttp.ClientSession) -> str:
    global rbn_api_hdr

    if rbn_api_hdr is not None:
        return rbn_api_hdr

    log.info("rbn header is unknown. pulling latest...")

    url = 'https://www.reversebeacon.net/spots.php'

    async with session.get(url) as response:
        if response.status == 400:
            # json response should be like: {"error":888,"ver_h":"d8999c"}
            j = await response.json()

            log.info(f"get rbn header resp: {json.dumps(j, indent=4)}")

            ver = j.get('ver_h')

            if ver:
                rbn_api_hdr = ver

            return rbn_api_hdr


async def query_rbn(
        session: aiohttp.ClientSession,
        calls: list[str],
        last_id: int):

    # h = returned as "ver_h": "2aa296" (version header)
    # ma = max age in seconds
    # m = 1 (CW)
    # bc = 1 (CQ)
    # s = last_id
    # r = max rows (100 is highest)
    # cdx = callsign to look for

    # get expected hdr from the api itself
    expected_ver = await get_rbn_header(session)

    calls = [urllib.parse.quote(call) for call in calls]
    url = f'https://www.reversebeacon.net/spots.php?h={expected_ver}&ma=60&m=1&bc=1&s={last_id}&r=100&cdx={",".join(calls)}'

    async with session.get(url) as response:
        if response.status == 200:
            j = await response.json()

            # log.info(f"rbn response {call} = {json.dumps(j, indent=4)}")

            ver = j.get('ver_h')

            if ver != expected_ver:
                log.warning(f'RBN API Version mismatch! Expected {expected_ver} but got {ver}')
                return [{
                    'activator': 'ERROR',
                    'frequency': 'ERROR',
                    'mode': 'CW',
                    'spotTime': datetime.now(timezone.utc),
                    'comments': '##ERROR##',  # hijack comment field for flag
                    'reference': '',
                    'name': 'Error RBN VERSION MISMATCH',
                    'locationDesc': ''
                }], 0

            spots = {}
            last_id = max(j.get('lastid_c'), last_id)
            for spot_id in sorted(j.get('spots', {})):
                spot = convert_rbn_to_pota_spot(j, spot_id)
                spots[spot['activator']] = spot
                last_id = max(int(spot_id), last_id)
            return list(spots.values()), last_id
        else:
            log.error(f"error getting spots from rbn: {response.status} {response.text}")
    return [], 0


def convert_rbn_to_pota_spot(j, spot):
    arr = j['spots'][spot]
    t = datetime.fromtimestamp(arr[10], tz=timezone.utc)
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
