""" Event parsing """
import json
import lzma
import os
import sys
import random

from helper import download_file_maybe
from config import get_events_url, get_events_filename, get_metadata_cache_path
from pyulog import ULog

#pylint: disable=wrong-import-position
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'libevents/libs/python'))
from libevents_parse.parser import Parser

#pylint: disable=invalid-name,global-statement

class FileCache:
    """ Very simple file cache with a maximum number of files """

    def __init__(self, path, max_num_files=1000):
        self._path = path
        self._max_num_files = max_num_files
        if not os.path.isdir(path):
            os.mkdir(path)

    def access(self, file_name):
        """ check if a file exists in the cache """
        return os.path.isfile(os.path.join(self._path, file_name))

    def insert(self, file_name, data):
        """ insert data (bytes) """
        # check cache size
        cache_files = os.listdir(self._path)
        if len(cache_files) >= self._max_num_files:
            # select a random file (could be improved to LRU)
            # (if flight review runs in multi-process mode, there's a minimal chance we delete a
            # file that's trying to be accessed by another instance)
            remove_index = random.randint(0, len(cache_files) - 1)
            os.remove(os.path.join(self._path, cache_files[remove_index]))

        # write
        with open(os.path.join(self._path, file_name), 'wb') as cache_file:
            cache_file.write(data)

    @property
    def path(self):
        """ Get configured path """
        return self._path

def get_event_definitions_from_log_file(ulog: ULog):
    """
    Get the event definitions json file from the log file.
    :return: path to json file or None
    """
    if 'metadata_events' in ulog.msg_info_multiple_dict and \
            'metadata_events_sha256' in ulog.msg_info_dict:
        file_hash = ulog.msg_info_dict['metadata_events_sha256']
        if len(file_hash) <= 64 and file_hash.isalnum():

            file_cache = FileCache(get_metadata_cache_path())
            events_metadata_filename = 'events.' + file_hash + '.json'
            if not file_cache.access(events_metadata_filename):
                # insert into the cache
                metadata_events_bytes = b''.join(ulog.msg_info_multiple_dict['metadata_events'][0])
                metadata_events_json = lzma.decompress(metadata_events_bytes)
                file_cache.insert(events_metadata_filename, metadata_events_json)

            return os.path.join(file_cache.path, events_metadata_filename)

    return None


__event_parser = None # fallback event parser, used if the log doesn't contain the event definitions
def get_event_parser(ulog: ULog):
    """ get event parser instance or None on error """
    events_profile = 'dev'

    event_definitions_json = get_event_definitions_from_log_file(ulog)
    if event_definitions_json is not None:
        with open(event_definitions_json, 'r', encoding="utf8") as json_file:
            p = Parser()
            p.load_definitions(json.load(json_file))
            p.set_profile(events_profile)
            return p

    # No json definitions in the log -> use global definitions
    global __event_parser
    events_json_xz = get_events_filename()
    # check for cached file update
    downloaded = download_file_maybe(events_json_xz, get_events_url())
    if downloaded == 2 or (downloaded == 1 and __event_parser is None):
        # decompress
        with lzma.open(events_json_xz, 'rt') as json_file:
            p = Parser()
            p.load_definitions(json.load(json_file))
            p.set_profile(events_profile)
            __event_parser = p

    return __event_parser


def get_logged_events(ulog):
    """
    Get the events as list of messages
    :return: list of (timestamp, time str, log level str, message) tuples
    """

    try:
        event_parser = get_event_parser(ulog)
    except Exception as e:
        print('Failed to get event parser: {}'.format(e))
        return []

    def event_log_level_str(log_level: int):
        return {0: 'EMERGENCY',
                1: 'ALERT',
                2: 'CRITICAL',
                3: 'ERROR',
                4: 'WARNING',
                5: 'NOTICE',
                6: 'INFO',
                7: 'DEBUG',
                8: 'PROTOCOL',
                9: 'DISABLED'}.get(log_level, 'UNKNOWN')

    def time_str(t):
        m1, s1 = divmod(int(t/1e6), 60)
        h1, m1 = divmod(m1, 60)
        return "{:d}:{:02d}:{:02d}".format(h1, m1, s1)

    # parse events
    messages = []
    try:
        events = ulog.get_dataset('event')
        all_ids = events.data['id']
        for event_idx, event_id in enumerate(all_ids):
            log_level = (events.data['log_levels'][event_idx] >> 4) & 0xf
            if log_level >= 8:
                continue
            args = []
            i = 0
            while True:
                arg_str = 'arguments[{}]'.format(i)
                if arg_str not in events.data:
                    break
                arg = events.data[arg_str][event_idx]
                args.append(arg)
                i += 1
            log_level_str = event_log_level_str(log_level)
            t = events.data['timestamp'][event_idx]
            event = None
            if event_parser is not None:
                event = event_parser.parse(event_id, bytes(args))
            if event is None:
                messages.append((t, time_str(t), log_level_str, \
                                 '[Unknown event with ID {:}]'.format(event_id)))
            else:
                # only show default group
                if event.group() == "default":
                    messages.append((t, time_str(t), log_level_str, event.message()))
            # we could expand this a bit for events:
            # - show the description too
            # - handle url's as link (currently it's shown as text, and all tags are escaped)
    except (KeyError, IndexError, ValueError) as error:
        # no events in log
        pass

    return messages
