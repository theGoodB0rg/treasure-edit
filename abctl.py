#!/usr/bin/env python
"""Convenience entry point:  python abctl.py <command> ..."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from cli.main import main

if __name__ == "__main__":
    main()
