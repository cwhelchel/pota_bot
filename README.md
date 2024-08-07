# POTA BOT

A Parks on the air Discord spot bot. Use it to post post spots from the main
POTA site into your Discord server.

## Docker Setup

This bot can be run from a docker image built and stored on docker hub at 
[krinkl3/spotbot](https://hub.docker.com/repository/docker/krinkl3/spotbot/general)

To run on low power ARM devices pull `krinkl3/spotbot:latest` or `krinkl3/spotbot:1.1`

For other architectures pull `krinkl3/spotbot:<version>-amd64`.

See the example docker-compose file below for a good starting point.

### Config Files

`callsigns.txt` is the main configuration file. It should contain a newline 
separated list of callsigns.

`schedule.json` is a secondary configuration file with a specific format. See the
example given in the source and modify to your needs. 
Note the times are in UTC so adjust days of week according to the day of week at UTC zone. The days of week value is Python numbered, so 0 == Monday ... 6 == Sunday.
<span style="vertical-align:super;font-size:0.8rem">👉 Consider this feature half-baked. I wouldn't put much trust in it.</span>

### Example docker-compose

This specific example runs on Ubuntu. Replace all the place holders with your
pertinent data. And place your schedule.json and callsigns.txt files in the same directory as your docker-compose.yml.

```docker
version: "3"
services:
  myradicalbot:
    image: krinkl3/spotbot:1.1-amd64
    volumes:
      - type: bind
        source: ./callsigns.txt
        target: /app/callsigns.txt
      - type: bind
        source: ./schedule.json
        target: /app/schedule.json
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

Then run: 

```bash
$ docker compose up -d
```

## Environment variables

The bot needs the following Environment variables set, (you will most likely
set them in your `docker-compose.yml`):

* `BOT_TOKEN` - The token generated by Discord when creating a bot
* `GUILD_ID` - The server's ID of where to bot needs to reside
* `CHANNEL_ID` - The channel ID where the bot will send spots
* `CALLSIGN_MGR_ROLE_ID` - The role ID for users to add/remove spots to tracking list
* `PING_ROLE_ID` - The role ID that will be pinged in spots
* `DISABLE_RBN`: '0' either a '1' or '0'. 1 will turn off querying of RBN spots.

> The id's should be integer values and are obtained through your discord client
> except for BOT_TOKEN which is generated via Discord's bot creation webpage. They 
> are still enclosed in quotes in the docker compose file.


### Building a local docker image
You can always build the docker images from source. Build the image like so:

```bash
$ docker build -t my_rad_bot . 
```

Use any name for the `-t` argument just remember to use it when deploying the 
docker image to a container.

