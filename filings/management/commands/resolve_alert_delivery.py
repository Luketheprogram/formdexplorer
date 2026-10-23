from django.core.management.base import BaseCommand,CommandError
from django.db import transaction
from django.utils import timezone
from filings.models import AlertDelivery,AlertPreference
from filings.alerts.service import worker_lock


class Command(BaseCommand):
    help='Resolve one held SMTP delivery after checking provider acceptance; never sends mail.'
    def add_arguments(self,parser):
        parser.add_argument('delivery_id',type=int)
        parser.add_argument('--outcome',required=True,choices=['accepted','not-accepted','cancel'])
        parser.add_argument('--note',required=True)
    def handle(self,*args,**opts):
        if len(opts['note'].strip())<10:raise CommandError('Supply a provider investigation note (at least 10 characters)')
        with worker_lock(), transaction.atomic():
            d=AlertDelivery.objects.filter(pk=opts['delivery_id']).first()
            if not d:raise CommandError('Unknown delivery')
            pref=AlertPreference.objects.select_for_update().get(user_id=d.user_id)
            d=AlertDelivery.objects.select_for_update().get(pk=d.pk)
            if d.state!='held':raise CommandError('Only held deliveries can be resolved')
            if opts['outcome']=='not-accepted' and not pref.email_enabled:raise CommandError('Recipient has unsubscribed')
            if opts['outcome']=='accepted':d.state='sent';d.sent_at=timezone.now()
            elif opts['outcome']=='not-accepted':d.state='retry';d.attempts=0;d.next_attempt_at=timezone.now()
            else:d.state='cancelled'
            d.resolution_note += f"\n{timezone.now().isoformat()} {opts['outcome']}: {opts['note'].strip()}"
            d.lease_until=None;d.save()
        self.stdout.write('Delivery resolution recorded; no email sent')
