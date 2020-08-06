from datetime import datetime

from celery import Celery
from celery.task import periodic_task
from django.conf import settings

from transfer.models import ScheduledPayment

app = Celery('tasks', broker=settings.REDIS_URL['LOCATION'])


@periodic_task(run_every=60,
               ignore_result=True,
               name='scheduled_payment')
def run_transfers_by_scheduled_payments():
    on_date = datetime.now()
    scheduled_payments = ScheduledPayment.objects.pending(
        on_date__lte=on_date
    )
    for scheduled_payment in scheduled_payments:
        scheduled_payment.create_transfer()
