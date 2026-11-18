#!/usr/bin/env python3
"""rolescan: one entry point for every platform-facing action."""
import sys

from cli.main import main

if __name__ == "__main__":
    sys.exit(main())
