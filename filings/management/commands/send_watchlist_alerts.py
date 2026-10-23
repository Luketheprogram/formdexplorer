"""Legacy entry point retained; default is now read-only and never sends mail."""
from .process_filing_alerts import Command as AlertCommand


class Command(AlertCommand):
    kinds=('watch',)
    help='Preview watchlist matches; use process_filing_alerts --send for combined delivery.'
