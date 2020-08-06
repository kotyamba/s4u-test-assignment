from decimal import Decimal

from django.db import models
from django.db.models import Sum


class Account(models.Model):
    number = models.PositiveIntegerField(unique=True)
    owner = models.ForeignKey('customer.Customer', models.CASCADE)
    balance = models.DecimalField(default=0, max_digits=18, decimal_places=2)
    reserved_amount = models.DecimalField(max_digits=18, decimal_places=2,
                                          default=Decimal(0))

    def get_max_transfer_amount(self) -> Decimal:
        """
        Returns max amount that Customer can use for Transfer
        """
        return self.balance - self.reserved_amount

    def get_reserved_amount_for_scheduled_payment(self) -> Decimal:
        """
        Gets all ScheduledPayment in status PENDING and calculates amount
        """
        from transfer.models import ScheduledPayment
        return self.scheduled_payment_in.filter(
            status=ScheduledPayment.Status.PENDING
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal(0)

    def update_reserved_amount(self) -> None:
        """
        Calculated reversed_amount by ScheduledPayment in status PENDING
        """
        self.reserved_amount = self.get_reserved_amount_for_scheduled_payment()
        self.save(update_fields=['reserved_amount'])
