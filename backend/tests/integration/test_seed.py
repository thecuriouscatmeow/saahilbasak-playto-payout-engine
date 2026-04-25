import pytest
from django.core.management import call_command
from apps.merchants.models import Merchant
from apps.payouts.models import Transaction
from apps.payouts.domain.enums import TxnType


@pytest.mark.django_db
def test_seed_creates_merchants():
    call_command("seed", verbosity=0)
    assert Merchant.objects.count() >= 2


@pytest.mark.django_db
def test_seed_creates_bank_accounts():
    from apps.merchants.models import BankAccount
    call_command("seed", verbosity=0)
    assert BankAccount.objects.count() >= 2


@pytest.mark.django_db
def test_seed_all_merchants_have_positive_balance():
    call_command("seed", verbosity=0)
    for merchant in Merchant.objects.all():
        total = Transaction.objects.filter(
            merchant=merchant, type=TxnType.CREDIT
        ).values_list("amount_paise", flat=True)
        assert sum(total) > 0


@pytest.mark.django_db
def test_seed_is_idempotent():
    call_command("seed", verbosity=0)
    call_command("seed", verbosity=0)
    assert Merchant.objects.count() == 3
