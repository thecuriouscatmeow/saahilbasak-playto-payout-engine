from decimal import Decimal
import pytest
from apps.payouts.domain.money import paise_to_rupees, rupees_to_paise, format_inr


def test_paise_to_rupees():
    assert paise_to_rupees(100) == Decimal("1.00")
    assert paise_to_rupees(12345678) == Decimal("123456.78")


def test_rupees_to_paise():
    assert rupees_to_paise(Decimal("1.00")) == 100
    assert rupees_to_paise("123456.78") == 12345678


def test_format_inr_basic():
    assert format_inr(100) == "₹1.00"


def test_format_inr_thousands():
    assert format_inr(100000) == "₹1,000.00"


def test_format_inr_lakhs():
    assert format_inr(12345678) == "₹1,23,456.78"


def test_format_inr_crores():
    assert format_inr(1234567800) == "₹1,23,45,678.00"
