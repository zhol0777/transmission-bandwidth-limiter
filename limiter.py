# pylint: disable=missing-function-docstring
"""
limiter.py
meant to be run as a cron job periodically
m    h dom mon dow command
*/15 * *   *   *   ./venv/bin/python limiter.py --sqlite-file test.sqlite3 --transmission-url \
    http://localhost:9091 --daily-limit 10g
"""

import argparse
import logging
from datetime import datetime, timedelta, timezone
from os import getenv
from urllib.parse import urlparse

import dotenv
import peewee
import transmission_rpc

data_units = {
    "b": 1,
    "k": 2**10,
    "m": 2**20,
    "g": 2**30,
    "t": 2**40,
}


time_units = {
    "m": 60,
    "h": 60 * 60,
    "d": 60 * 60 * 24,
    "w": 60 * 60 * 24 * 7
}

log = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter('[%(levelname)s] [%(asctime)s] - %(message)s')
handler.setFormatter(formatter)
log.addHandler(handler)


def pretty_print_bytes(byte_amount: int) -> str:
    min_val, max_denomination = None, ''
    for unit_letter, size in data_units.items():
        val = byte_amount / size
        if (min_val is None) or (val < min_val and val >= 1):  # pylint: disable=chained-comparison
            min_val = val
            max_denomination = unit_letter
    return f"{min_val:.2f}{max_denomination}".upper()


def parse_size(size: str, metric: str) -> int:
    """
    :param size: String to parse into integer value (ex. '40m', '500G', '30d')
    :param metric: 'DATA' or 'TIME'
    """
    size = size.lower()
    number = float(''.join([char for char in size if (char.isdigit() or char == '.')]))
    match metric:
        case 'TIME':
            units = time_units
        case 'DATA':
            units = data_units
        case _:
            raise ValueError("Metric must be 'TIME' or 'DATA'")
    try:
        unit = next(char for char in size if char in units)
    except StopIteration:
        raise ValueError("Must be formatted '5.5T', '500G', '1000M'")  # pylint: disable=raise-missing-from
    return int(number * units[unit])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite-file", required=True)
    parser.add_argument("--transmission-url", required=True, help="ex. http://localhost:9091")
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--monthly-limit")
    parser.add_argument("--weekly-limit")
    parser.add_argument("--daily-limit")
    parser.add_argument("--debug", action='store_true')
    namespace = parser.parse_args()
    if not any([namespace.monthly_limit, namespace.weekly_limit, namespace.daily_limit]):
        raise ValueError("Limit needs to be applied! "
                         "Please run `./limiter.py -h` for more information")
    return namespace


class TimeSlice(peewee.Model):
    """
    Schema for tracking data usage over time
    """
    timestamp = peewee.DateTimeField(index=True, unique=True)
    data_usage = peewee.BigIntegerField()

    class Meta:  # pylint: disable=too-few-public-methods
        '''connects model to db'''
        database = peewee.SqliteDatabase(parse_args().sqlite_file)


def should_throttle(db: peewee.SqliteDatabase, past_reference: datetime,
                    current_data_usage: int, usage_limit: str) -> bool:
    with db:
        try:
            past_slice = TimeSlice.select().where(
                TimeSlice.timestamp < past_reference).order_by(TimeSlice.timestamp.desc()).get()
        except peewee.DoesNotExist:
            log.debug("No time slice old enough to meet requirements found, using oldest slice")
            try:
                past_slice = TimeSlice.select().order_by(TimeSlice.timestamp.asc()).get()
            except peewee.DoesNotExist:
                log.debug("TimeSlice table unpopulated! No determination can be made")
                return False
        delta = current_data_usage - past_slice.data_usage
        utc_time = datetime.strptime(past_slice.timestamp, '%Y-%m-%d %H:%M:%S.%f%z')
        log.debug("%s has been used since %s", pretty_print_bytes(delta),
                  utc_time.astimezone())
        if delta > parse_size(usage_limit, metric='DATA'):
            return True
    return False


def main() -> None:
    """
    run limiter
    """
    args = parse_args()
    if args.debug:
        log.setLevel(logging.DEBUG)
    parsed_url = urlparse(args.transmission_url)
    dotenv.load_dotenv(args.env_file)

    host = parsed_url.netloc.split(':')[0]
    protocol = 'https' if parsed_url.scheme == 'https' else 'http'
    port = parsed_url.port or (443 if protocol == 'https' else 80)

    transmission_client = transmission_rpc.Client(host=host, port=port,
                                                  protocol=protocol,  # type: ignore
                                                  username=getenv('TRANSMISSION_USERNAME'),
                                                  password=getenv('TRANSMISSION_PASSWORD'))
    session_stats = transmission_client.session_stats().fields
    current_data_usage = session_stats.get('cumulative-stats', {}).get('downloadedBytes', 0) + \
        session_stats.get('cumulative-stats', {}).get('uploadedBytes', 0)
    db = peewee.SqliteDatabase(args.sqlite_file)
    db.create_tables([TimeSlice])
    now = datetime.now(timezone.utc)
    throttle = False
    with db:
        if args.daily_limit:
            throttle |= should_throttle(db, now - timedelta(days=1),
                                        current_data_usage, args.daily_limit)
        if args.weekly_limit:
            throttle |= should_throttle(db, now - timedelta(weeks=1),
                                        current_data_usage, args.weekly_limit)
        if args.monthly_limit:
            throttle |= should_throttle(db, now - timedelta(days=30),
                                        current_data_usage, args.monthly_limit)
        is_throttled = transmission_client.get_session().alt_speed_enabled
        log.debug("Should throttle: %s, current throttling state: %s", throttle, is_throttled)
        if throttle and not transmission_client.get_session().alt_speed_enabled:
            log.warning("Activate alt speed on Transmission...")
            transmission_client.set_session(alt_speed_enabled=True)
        elif transmission_client.get_session().alt_speed_enabled and not throttle:
            log.info("De-activate alt speed on Transmission...")
            transmission_client.set_session(alt_speed_enabled=False)
        TimeSlice(timestamp=now, data_usage=current_data_usage).save()


if __name__ == '__main__':
    main()
