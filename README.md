# POTA BOT

A Parks on the air Discord spot bot. Use it to post post spots from the main
POTA site into your Discord server.

## Docker

This bot can be run in a docker container. Build the image like so:

```bash
$ docker build -t my_rad_bot . 
```

Use any name for the `-t` argument just remember to use it when deploying the 
docker image to a container.


## Environment variables

The bot needs the following Environment variables set, (you will most likely
set them in your `docker-compose.yml`):

* `BOT_TOKEN` - The token generated by Discord when creating a bot
* `GUILD_ID` - The server's ID of where to bot needs to reside
* `CHANNEL_ID` - The channel ID where the bot will send spots
* `CALLSIGN_MGR_ROLE_ID` - The role ID for users to add/remove spots to tracking list
* `PING_ROLE_ID` - The role ID that will be pinged in spots

> The id's should be integer values and are obtained through your discord client
> except for BOT_TOKEN which is generated via Discord's bot creation webpage.

## Example docker-compose

Callsigns.txt should contain a newline separated list of callsigns to look for.

```docker
version: "3"
services:
  myradicalbot:
    image: my_rad_bot:latest
    volumes:
      - type: bind
        source: ./callsigns.txt
        target: /app/callsigns.txt
    environment:
      TZ: America/New_York
      BOT_TOKEN: "bot token here" # the generated discord bot token
      GUILD_ID: "server id here"  # the snowflake id of your guild
      CHANNEL_ID: "channel id here"  # channel id to post in
      CALLSIGN_MGR_ROLE_ID: "role id here"  # id of role to add/remove callsigns
      PING_ROLE_ID: "role id here"  # id of role to ping in spot embeds
      DISABLE_RBN: '0'
    restart: unless-stopped
```