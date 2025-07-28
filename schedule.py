from datetime import datetime, timezone
import json
import logging
import re
from threading import Lock

import discord

log = logging.getLogger("discord")
sched_lock = Lock()


class Schedule:

    def __init__(self, data):
        self.data = data

    @property
    def messages(self):
        return self.data

    def time_to_send_msg(self, msg) -> bool:
        now = datetime.now(timezone.utc)
        weekday = now.date().weekday()

        is_enabled = msg.get('enabled')

        if is_enabled is not None and is_enabled == 0:
            return False

        if weekday == msg['dow']:
            msg_time = msg['time_utc'].split(':')
            if now.hour == int(msg_time[0]) and now.minute == int(msg_time[1]):
                return True

        return False

    def set_msg_time(self, msg_name, time, dow: int = -1) -> bool:
        pattern = r'^([01][0-9]|2[0-3]):([0-5][0-9])$'

        if re.match(pattern, time):
            for msg in self.messages:
                if (msg['name'] == msg_name):
                    msg['time_utc'] = time
                    msg['dow'] = dow if dow > 0 else msg['dow']
        else:
            return False

        with sched_lock:
            with open(file="schedule.json", mode='w', encoding='utf8') as w:
                json.dump(self.messages, w, indent=4)
                return True

    def set_msg_content(self, msg_name, text, embed: str = "") -> bool:
        for msg in self.messages:
            if (msg['name'] == msg_name):
                msg['msg'] = [text]
                if len(embed) > 0:
                    msg['embeds'] = json.loads(embed)

        with sched_lock:
            with open(file="schedule.json", mode='w', encoding='utf8') as w:
                json.dump(self.messages, w, indent=4)
                return True
        return False

    def set_msg_enabled(self, msg_name: str, value: int) -> bool:
        for msg in self.messages:
            if (msg['name'] == msg_name):
                if (value < 0 or value > 1):
                    raise ValueError('value must be 0 or 1')
                msg['enabled'] = value

        with sched_lock:
            with open(file="schedule.json", mode='w', encoding='utf8') as w:
                json.dump(self.messages, w, indent=4)
                return True
        return False

    @staticmethod
    def get_schedule():
        if sched_lock.locked():
            return None
        obj = None
        try:
            with open(file="schedule.json", mode="r", encoding='utf8') as f:
                lines = f.read()
                obj = json.loads(lines)
        except Exception as ex:
            log.error("Error getting schedule file", exc_info=ex)
            raise
        return Schedule(obj)

    @staticmethod
    def get_scheduled_msg(json):
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
        return msg_content, embeds
