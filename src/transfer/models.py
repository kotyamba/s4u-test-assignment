from decimal import Decimal

from django.db import models, transaction
from django.db.models import F
from django.utils import timezone

from account.models import Account
from transfer.exceptions import (NegativeAmountException,
                                 InsufficientBalance)
from transfer.managers import ScheduledPaymentManager


class Transfer(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    from_account = models.ForeignKey(Account, models.CASCADE,
                                     related_name='transfers_in')
    to_account = models.ForeignKey(Account, models.CASCADE,
                                   related_name='transfers_out')
    amount = models.DecimalField(max_digits=18, decimal_places=2)

    @staticmethod
    @transaction.atomic
    def do_transfer(from_account: Account,
                    to_account: Account,
                    amount: Decimal):
        if amount < 0:
            raise NegativeAmountException

        if from_account.balance < amount:
            raise InsufficientBalance()

        # For SQLight we can use only transactions.
        # But I expect that production will use PostgreSQL instead SQLight.
        Account.objects.select_for_update().filter(pk=from_account.pk).update(
            balance=F('balance') - amount)
        Account.objects.select_for_update().filter(pk=to_account.pk).update(
            balance=F('balance') + amount)

        return Transfer.objects.create(
            from_account=from_account,
            to_account=to_account,
            amount=amount
        )


class ScheduledPayment(models.Model):
    """
    Class make ability to create scheduled payment
    """

    class Status(models.IntegerChoices):
        PENDING = 0, 'pending'
        DONE = 1, 'done'
        CANCELED = 2, 'canceled'
        FAILED = 3, 'failed'

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    from_account = models.ForeignKey(Account, models.CASCADE,
                                     related_name='scheduled_payment_in')
    to_account = models.ForeignKey(Account, models.CASCADE,
                                   related_name='scheduled_payment_out')
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    status = models.IntegerField(choices=Status.choices,
                                 default=Status.PENDING)
    transfer = models.ForeignKey(Transfer, models.CASCADE,
                                 related_name='scheduled', null=True)

    on_date = models.DateTimeField()

    objects = ScheduledPaymentManager()

    @staticmethod
    @transaction.atomic
    def create_scheduled_transfer(from_account: Account,
                                  to_account: Account,
                                  amount: Decimal,
                                  on_date: timezone.datetime.date):
        """
        Creates ScheduledPayment if amount > 0 and allowed balance in Account
        """
        if amount < 0:
            raise NegativeAmountException

        if from_account.get_max_transfer_amount() < amount:
            raise InsufficientBalance

        Account.objects.select_for_update().filter(pk=from_account.pk).update(
            reserved_amount=F('reserved_amount') + amount)
        return ScheduledPayment.objects.create(from_account=from_account,
                                               to_account=to_account,
                                               amount=amount,
                                               on_date=on_date)

    @transaction.atomic
    def create_transfer(self) -> None:
        """
        Call do_transfer with logic for ScheduledPayment
        """
        status = ScheduledPayment.Status.DONE
        try:
            transfer = Transfer.do_transfer(from_account=self.from_account,
                                            to_account=self.to_account,
                                            amount=self.amount)
            self.transfer = transfer
            self.save(update_fields=['transfer'])
        except InsufficientBalance:
            status = ScheduledPayment.Status.FAILED
        Account.objects.select_for_update().filter(
            pk=self.from_account.pk).update(
            reserved_amount=F('reserved_amount') - self.amount)
        self.status = status
        self.save(update_fields=['status'])

    @transaction.atomic()
    def cancel(self) -> None:
        """
        Set status into CANCELED and update reserved_amount for Account
        """
        Account.objects.select_for_update().filter(
            pk=self.from_account.pk).update(
            reserved_amount=F('reserved_amount') - self.amount)
        self.status = ScheduledPayment.Status.CANCELED
        self.save(update_fields=['status'])

    def delete(self, *args, **kwargs):
        """
        Set status into CANCELED and update reserved_amount for Account
        """
        self.cancel()

# Account/transfer schema evolution
# For example it can be implemented following:
# - Make django's app with name Bank. Bank(models.Model). Add needs fields and methods for descriptions, permissions and etc.
# - In the Account model add field "bank" for relate with Banks.
# - Perhaps also add the field "currency" into Account. And add methods to make exchange between currencies.
# - In the model Transfer add field "type" and methods debit/credit/withdraw/refund for implement types of transfers.
# - Also I think the best way will be disable ability make delete Transfers, something like in ScheduledPayment.
