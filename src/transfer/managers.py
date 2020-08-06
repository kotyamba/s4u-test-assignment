from django.contrib.auth.models import models
from django.db.models import manager


class ScheduledPaymentQuerySet(models.QuerySet):

    def delete(self):
        from transfer.exceptions import DeleteEntityException
        raise DeleteEntityException


class ScheduledPaymentManager(manager.Manager):
    def get_queryset(self):
        return ScheduledPaymentQuerySet(self.model, using=self._db)

    def pending(self, **kwargs):
        from .models import ScheduledPayment
        kwargs['status'] = ScheduledPayment.Status.PENDING
        return super().get_queryset().filter(**kwargs)

    def canceled(self, **kwargs):
        from .models import ScheduledPayment
        kwargs['status'] = ScheduledPayment.Status.CANCELED
        return super().get_queryset().filter(**kwargs)
