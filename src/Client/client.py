#!/usr/bin/python3

"""H3XRecon Client

Usage:
    client.py (domains | ips | urls) [-p <program>]

Options:
    -p --program     Program to work on.
"""

import os
import sys
import json
import re
from urllib.parse import urlparse
from docopt import docopt

VERSION = "0.0.1"

class H3XReconClient:
    arguments = None
    
    def __init__(self, arguments):
        # Initialize arguments only if properly parsed by docopt
        if arguments:
            self.arguments = arguments
        else:
            raise ValueError("Invalid arguments provided.")

    def run(self):
        # Execute based on parsed arguments
        if self.arguments.get('domains'):
            print(f'domains  {self.arguments['<program>'][0]}')
        elif self.arguments.get('ips'):
            print('ips')
        elif self.arguments.get('urls'):
            print('urls')
        else:
            raise ValueError("No valid argument found in 'domains', 'ips', or 'urls'.")

def process_stdin():
    # Process standard input and filter out empty lines
    return list(filter(lambda x: not re.match(r'^\s*$', x),  sys.stdin.read().split('\n')))

def main():
    try:
        # Parse arguments
        arguments = docopt(__doc__, argv=sys.argv[1:], version=VERSION)
        # Pass parsed arguments to H3XReconClient
        client = H3XReconClient(arguments)
        client.run()
    except Exception as e:
        print('[ERROR] ' + str(e))
            
if __name__ == '__main__':
    main()
