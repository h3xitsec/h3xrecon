#!/usr/bin/env python3

"""H3XRecon Client

Usage:
    h3xrecon ( program ) ( list )
    h3xrecon ( program ) ( add | del) ( <program> )
    h3xrecon [ -p <program> ] ( config ) ( add | del ) ( cidr | scope ) ( - | <item> )
    h3xrecon [ -p <program> ] ( config ) ( list ) ( cidr | scope )
    h3xrecon ( system ) ( queue ) ( show | messages | flush ) ( worker | job | data )
    h3xrecon ( system ) ( compose ) ( status | start | stop )
    h3xrecon [ -p <program> ] ( list ) ( domains | ips ) [--resolved] [--unresolved]
    h3xrecon [ -p <program> ] ( list ) ( urls | services ) [--details]
    h3xrecon [ -p <program> ] ( add | del ) ( domain | ip | url ) ( - | <item> )
    h3xrecon [ -p <program> ] ( sendjob ) ( <function> ) ( <target> ) [--force]

Options:
    -p --program     Program to work on.
    --resolved       Show only resolved items.
    --unresolved    Show only unresolved items.
    --force         Force execution of job.
    --details       Show details about URLs.
"""

import asyncio
import sys, os
from docopt import docopt
from h3xrecon.cli.client import H3XReconClient

VERSION = "0.0.1"



def main():
    try:
        # Parse arguments
        arguments = docopt(__doc__, argv=sys.argv[1:], version=VERSION)
        # Pass parsed arguments to H3XReconClient
        client = H3XReconClient(arguments)
        asyncio.run(client.run())
    except Exception as e:
        print('[ERROR] ' + str(e))

if __name__ == '__main__':
    main()
