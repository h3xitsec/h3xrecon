#!/usr/bin/env python3

"""H3XRecon Client

Usage:
    h3xrecon ( program ) ( l | list )
    h3xrecon ( program ) ( a | add | d | del) ( <program> )
    h3xrecon [ -p <program> ] ( config ) ( a | add | d | del ) ( cidr | scope ) ( - | <item> )
    h3xrecon [ -p <program> ] ( config ) ( l | list ) ( cidr | scope )
    h3xrecon ( system ) ( queue ) ( show | messages | flush ) ( worker | job | data )
    h3xrecon ( system ) ( compose ) ( status | start | stop )
    h3xrecon [ -p <program> ] ( l | list ) ( d | domains | i | ips ) [--resolved] [--unresolved]
    h3xrecon [ -p <program> ] ( l | list ) ( u | urls | s | services ) [--details]
    h3xrecon [ -p <program> ] ( a | add | d | del ) ( d | domain | i | ip | u | url ) ( - | <item> )
    h3xrecon [ -p <program> ] ( s | sendjob ) ( <function> ) ( <target> ) [--force]

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
