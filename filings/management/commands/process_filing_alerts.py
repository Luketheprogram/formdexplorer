import json
from django.core.management.base import BaseCommand, CommandError
from filings.alerts.service import process


class Command(BaseCommand):
    help='Preview (default), enqueue, or deliver deduplicated saved-search/watchlist digests.'
    kinds=('search','watch')

    def add_arguments(self,parser):
        modes=parser.add_mutually_exclusive_group()
        modes.add_argument('--dry-run',action='store_true')
        modes.add_argument('--enqueue-only',action='store_true')
        modes.add_argument('--send',action='store_true')

    def handle(self,*args,**opts):
        try:
            stats=process(send=opts['send'],dry_run=not(opts['send'] or opts['enqueue_only']),kinds=self.kinds)
        except (RuntimeError,ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(stats,sort_keys=True))
        if stats.get('invalid'):
            self.stderr.write('Skipped saved search: invalid filters; see saved-search status')
        if opts['send'] and any(stats.get(k) for k in ['invalid','held','retry','recovered_to_hold']):
            raise CommandError('Some alerts need attention; see queue health report')
