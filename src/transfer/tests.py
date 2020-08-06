from decimal import Decimal

from django.db.models import Sum
from django.test import TestCase
from django.utils import timezone

from account.models import Account
from customer.models import Customer
from transfer.exceptions import NegativeAmountException, DeleteEntityException
from transfer.models import (Transfer,
                             ScheduledPayment,
                             InsufficientBalance)


class TransferTest(TestCase):
    def setUp(self):
        super(TransferTest, self).setUp()

        customer = Customer.objects.create(
            email='test@test.invalid',
            full_name='Test Customer',
        )

        self.account1 = Account.objects.create(number=123, owner=customer,
                                               balance=1000)
        self.account2 = Account.objects.create(number=456, owner=customer,
                                               balance=1000)

    def test_basic_transfer(self):
        Transfer.do_transfer(self.account1, self.account2, 100)
        self.account1.refresh_from_db()
        self.account2.refresh_from_db()
        self.assertEqual(self.account1.balance, 900)
        self.assertEqual(self.account2.balance, 1100)
        self.assertTrue(Transfer.objects.filter(
            from_account=self.account1,
            to_account=self.account2,
            amount=100,
        ).exists())

    def test_not_enough_balance(self):
        self.assertRaises(InsufficientBalance,
                          Transfer.do_transfer,
                          self.account1,
                          self.account2,
                          Decimal(10000))

    def test_negative_amount(self):
        self.assertRaises(NegativeAmountException,
                          Transfer.do_transfer,
                          self.account1,
                          self.account2,
                          Decimal(-1))


class ScheduledPaymentTest(TestCase):
    def setUp(self):
        super().setUp()
        customer = Customer.objects.create(
            email='test@test.invalid',
            full_name='Test Customer',
        )

        self.account1 = Account.objects.create(number=123, owner=customer,
                                               balance=1000)
        self.account2 = Account.objects.create(number=456, owner=customer,
                                               balance=1000)
        self.on_date = (timezone.datetime.now(tz=timezone.utc) +
                        timezone.timedelta(days=10))

    def test_scheduled_payment(self):
        amount = Decimal(100)
        ScheduledPayment.create_scheduled_transfer(from_account=self.account1,
                                                   to_account=self.account2,
                                                   amount=amount,
                                                   on_date=self.on_date)
        self.assertTrue(ScheduledPayment.objects.filter(
            from_account=self.account1,
            to_account=self.account2,
            amount=amount,
        ).exists())
        self.account1.refresh_from_db()
        self.assertEqual(amount, self.account1.reserved_amount)

    def test_create_transfer(self):
        amount = Decimal(100)
        scheduled_payment = ScheduledPayment.create_scheduled_transfer(
            from_account=self.account1,
            to_account=self.account2,
            amount=amount,
            on_date=self.on_date)
        self.account1.refresh_from_db()
        self.assertEqual(amount, self.account1.reserved_amount)
        self.assertIsNone(scheduled_payment.transfer)
        scheduled_payment.create_transfer()
        self.account1.refresh_from_db()
        self.assertIsNotNone(scheduled_payment.transfer)
        self.assertEqual(0, self.account1.reserved_amount)

    def test_not_enough_balance(self):
        self.assertRaises(InsufficientBalance,
                          ScheduledPayment.create_scheduled_transfer,
                          self.account1,
                          self.account2,
                          Decimal(10000),
                          self.on_date)

    def test_get_max_transfer_amount(self):
        amount = Decimal(100)
        for i in range(10):
            ScheduledPayment.create_scheduled_transfer(
                from_account=self.account1,
                to_account=self.account2,
                amount=amount,
                on_date=self.on_date)
            allowed_max_transfer_amount = (
                    self.account1.balance - ScheduledPayment.objects.filter(
                from_account=self.account1,
                status=ScheduledPayment.Status.PENDING).aggregate(
                Sum('amount'))['amount__sum'])
            self.account1.refresh_from_db()
            self.assertEqual(allowed_max_transfer_amount,
                             self.account1.get_max_transfer_amount())

    def test_negative_amount(self):
        self.assertRaises(NegativeAmountException,
                          ScheduledPayment.create_scheduled_transfer,
                          self.account1,
                          self.account2,
                          Decimal(-1),
                          self.on_date)

    def test_delete_entities(self):
        amount = Decimal(100)
        for i in range(10):
            ScheduledPayment.create_scheduled_transfer(
                from_account=self.account1,
                to_account=self.account2,
                amount=amount,
                on_date=self.on_date)
        self.assertRaises(DeleteEntityException,
                          ScheduledPayment.objects.all().delete)

    def test_delete_entity(self):
        count_scheduled_payments = 10
        for i in range(count_scheduled_payments):
            ScheduledPayment.create_scheduled_transfer(
                from_account=self.account1,
                to_account=self.account2,
                amount=Decimal(100),
                on_date=self.on_date)
        self.assertEqual(count_scheduled_payments,
                         ScheduledPayment.objects.count())
        last_scheduled_payment = ScheduledPayment.objects.last()
        self.assertEqual(ScheduledPayment.Status.PENDING,
                         last_scheduled_payment.status)
        last_scheduled_payment.delete()
        self.assertEqual(ScheduledPayment.Status.CANCELED,
                         last_scheduled_payment.status)
        last_scheduled_payment.from_account.refresh_from_db()
        self.assertEqual(last_scheduled_payment.from_account.
                         get_reserved_amount_for_scheduled_payment(),
                         last_scheduled_payment.from_account.reserved_amount)

    def test_cancel_entity(self):
        scheduled_payment = ScheduledPayment.create_scheduled_transfer(
            from_account=self.account1,
            to_account=self.account2,
            amount=Decimal(100),
            on_date=self.on_date)
        self.assertTrue(ScheduledPayment.objects.exists())
        self.assertEqual(ScheduledPayment.Status.PENDING,
                         scheduled_payment.status)
        scheduled_payment.cancel()
        scheduled_payment.refresh_from_db()
        self.assertEqual(ScheduledPayment.Status.CANCELED,
                         scheduled_payment.status)
        scheduled_payment.from_account.refresh_from_db()
        self.assertEqual(scheduled_payment.from_account.
                         get_reserved_amount_for_scheduled_payment(),
                         scheduled_payment.from_account.reserved_amount)

    def test_pending_status(self):
        count_scheduled_payments = 100
        for i in range(count_scheduled_payments):
            ScheduledPayment.create_scheduled_transfer(
                from_account=self.account1,
                to_account=self.account2,
                amount=Decimal(1),
                on_date=self.on_date)
        on_date = timezone.datetime.now(tz=timezone.utc)
        scheduled_payments = ScheduledPayment.objects.pending(
            on_date__gte=on_date
        )
        self.assertEqual(count_scheduled_payments, scheduled_payments.count())
