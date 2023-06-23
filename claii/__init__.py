import sys
if not '-m' in sys.argv:
    from .cli import cli
