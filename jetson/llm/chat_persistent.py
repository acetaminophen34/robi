#!/usr/bin/env python3
"""Compatibility entrypoint. The persistent implementation now lives in chat.py."""
import sys
from chat import main

if __name__ == '__main__':
    sys.exit(main())
