# transmission-bandwidth-limiter

```
╰─ python3 ./limiter.py
usage: limiter.py [-h] --sqlite-file SQLITE_FILE --transmission-url TRANSMISSION_URL --env-file ENV_FILE [--monthly-limit MONTHLY_LIMIT]
                  [--weekly-limit WEEKLY_LIMIT] [--daily-limit DAILY_LIMIT] [--debug]
limiter.py: error: the following arguments are required: --sqlite-file, --transmission-url, --env-file
```

* either set up venv, or install python packages
  * transmission-rpc
  * peewee
  * python-dotenv
* run periodically, maybe through a cron job. something like this maybe
  * ```*/15 * *   *   *   ./venv/bin/python limiter.py --sqlite-file test.sqlite3 --transmission-url http://localhost:9091 --daily-limit 10g --env-file .env```

## env file

fill accordingly:

```
TRANSMISSION_USERNAME=XXXXXXXXXX
TRANSMISSION_PASSWORD=XXXXXXXXXX
```