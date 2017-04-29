#! /usr/bin/env python3
""" Script to run the bokeh server """

from __future__ import absolute_import
from __future__ import print_function

import argparse
import os
import sys

from bokeh.application import Application
from bokeh.server.server import Server
from bokeh.application.handlers import DirectoryHandler
# this is needed for the following imports
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'plot_app'))
from helper import set_log_id_is_filename, print_cache_info
from config import debug_print_timing
from tornado_handlers import DownloadHandler, UploadHandler, BrowseHandler, \
    EditEntryHandler

#pylint: disable=invalid-name

def _fixup_deprecated_host_args(arguments):
    # --host is deprecated since bokeh 0.12.5. You might want to use
    # --allow-websocket-origin instead
    if arguments.host is not None and len(arguments.host) > 0:
        if arguments.allow_websocket_origin is None:
            arguments.allow_websocket_origin = []
        arguments.allow_websocket_origin += arguments.host
        arguments.allow_websocket_origin = list(set(arguments.allow_websocket_origin))

parser = argparse.ArgumentParser(description='Start bokeh Server')

parser.add_argument('-s', '--show', dest='show', action='store_true',
                    help='Open browser on startup')
parser.add_argument('-f', '--file', metavar='file.ulg', action='store',
                    help='Directly show an ULog file, only for local use (implies -s)',
                    default=None)
parser.add_argument('--num-procs', dest='numprocs', type=int, action='store',
                    help="""Number of worker processes. Default to 1.
                    0 will autodetect number of cores""",
                    default=1)
parser.add_argument('--port', type=int, action='store',
                    help='Port to listen on', default=None)
parser.add_argument('--address', action='store',
                    help='Network address to listen to', default=None)
parser.add_argument('--host', action='append', type=str, metavar='HOST[:PORT]',
                    help="""Hosts whitelist, that must match the Host header in new
                    requests. It has the form <host>[:<port>]. If no port is specified, 80
                    is used. You should use the DNS name of the public endpoint here. \'*\'
                    matches all hosts (for testing only) (default=localhost)""",
                    default=None)
parser.add_argument('--allow-websocket-origin', action='append', type=str, metavar='HOST[:PORT]',
                    help="""Public hostnames which may connect to the Bokeh websocket""",
                    default=None)

args = parser.parse_args()

# This should remain here until --host is removed entirely
_fixup_deprecated_host_args(args)

applications = {}
main_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'plot_app')
handler = DirectoryHandler(filename=main_path)
applications['/plot_app'] = Application(handler)

server_kwargs = {}
if args.port != None: server_kwargs['port'] = args.port
server_kwargs['num_procs'] = args.numprocs
if args.address != None: server_kwargs['address'] = args.address
if args.host != None: server_kwargs['host'] = args.host
if args.allow_websocket_origin != None:
    server_kwargs['allow_websocket_origin'] = args.allow_websocket_origin


show_ulog_file = False
if args.file != None:
    ulog_file = os.path.abspath(args.file)
    show_ulog_file = True
    args.show = True
set_log_id_is_filename(show_ulog_file)


# additional request handlers
extra_patterns = [
    (r'/upload', UploadHandler),
    (r'/browse', BrowseHandler),
    (r'/edit_entry', EditEntryHandler),
    (r'/?', UploadHandler), #root should point to upload
    (r'/download', DownloadHandler)
]

server = Server(applications, extra_patterns=extra_patterns, **server_kwargs)

if args.show:
    # we have to defer opening in browser until we start up the server
    def show_callback():
        """ callback to open a browser window after server is fully initialized"""
        if show_ulog_file:
            server.show('/plot_app?log='+ulog_file)
        else:
            server.show('/upload')
    server.io_loop.add_callback(show_callback)


if debug_print_timing():
    def print_statistics():
        """ print ulog cache info once per hour """
        print_cache_info()
        server.io_loop.call_later(60*60, print_statistics)
    server.io_loop.call_later(60, print_statistics)

# run_until_shutdown has been added 0.12.4 and is the preferred start method
run_op = getattr(server, "run_until_shutdown", None)
if callable(run_op):
    server.run_until_shutdown()
else:
    server.start()

