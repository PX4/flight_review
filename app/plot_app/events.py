""" Event parsing """
import json
import lzma
from typing import Optional, Any, List, Tuple

from helper import download_file_maybe
from config import get_events_url, get_events_filename
from pyulog import ULog
from pyulog.px4_events import PX4Events

# pylint: disable=global-statement
__event_parser: PX4Events = None  # Keep the parser to cache the default event definitions


def get_logged_events(ulog: ULog) -> List[Tuple[int, str, str]]:
    """
    Get the events as list of messages
    :return: list of (timestamp, log level str, message) tuples
    """

    def get_default_json_definitions(already_has_default_parser: bool) -> Optional[Any]:
        """ Retrieve the default json event definitions """

        events_json_xz = get_events_filename()
        # Check for cached file update
        downloaded = download_file_maybe(events_json_xz, get_events_url())
        if downloaded == 2 or (downloaded == 1 and not already_has_default_parser):
            # Decompress
            with lzma.open(events_json_xz, 'rt') as json_file:
                return json.load(json_file)

        return None

    global __event_parser
    if __event_parser is None:
        __event_parser = PX4Events()
        __event_parser.set_default_json_definitions_cb(get_default_json_definitions)

    return __event_parser.get_logged_events(ulog)
