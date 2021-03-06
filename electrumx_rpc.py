#!/usr/bin/env python3
#
# Copyright (c) 2016, Neil Booth
#
# All rights reserved.
#
# See the file "LICENCE" for information about the copyright
# and warranty status of this software.

'''Script to send RPC commands to a running ElectrumX server.'''


import argparse
import asyncio
import json
from functools import partial
from os import environ

from lib.jsonrpc import JSONRPC
from server.controller import Controller


class RPCClient(JSONRPC):

    def __init__(self):
        super().__init__()
        self.queue = asyncio.Queue()
        self.max_send = 1000000

    def enqueue_request(self, request):
        self.queue.put_nowait(request)

    async def send_and_wait(self, method, params, timeout=None):
        # Raise incoming buffer size - presumably connection is trusted
        self.max_buffer_size = 5000000
        if params:
            params = [params]
        payload = self.request_payload(method, id_=method, params=params)
        self.encode_and_send_payload(payload)

        future = asyncio.ensure_future(self.queue.get())
        for f in asyncio.as_completed([future], timeout=timeout):
            try:
                request = await f
            except asyncio.TimeoutError:
                future.cancel()
                print('request timed out after {}s'.format(timeout))
            else:
                await request.process(self)

    async def handle_response(self, result, error, method):
        if result and method in ('groups', 'sessions'):
            for line in Controller.text_lines(method, result):
                print(line)
        else:
            value = {'error': error} if error else result
            print(json.dumps(value, indent=4, sort_keys=True))


def main():
    '''Send the RPC command to the server and print the result.'''
    parser = argparse.ArgumentParser('Send electrumx an RPC command' )
    parser.add_argument('-p', '--port', metavar='port_num', type=int,
                        help='RPC port number')
    parser.add_argument('command', nargs=1, default=[],
                        help='command to send')
    parser.add_argument('param', nargs='*', default=[],
                        help='params to send')
    args = parser.parse_args()

    if args.port is None:
        args.port = int(environ.get('RPC_PORT', 8000))

    loop = asyncio.get_event_loop()
    coro = loop.create_connection(RPCClient, 'localhost', args.port)
    try:
        transport, protocol = loop.run_until_complete(coro)
        coro = protocol.send_and_wait(args.command[0], args.param, timeout=15)
        loop.run_until_complete(coro)
    except OSError:
        print('error connecting - is ElectrumX catching up or not running?')
    finally:
        loop.close()


if __name__ == '__main__':
    main()
