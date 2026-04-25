from apps.payouts.domain.money import request_hash


def test_request_hash_stability():
    body = {"amount": 1000, "account_id": "abc", "merchant_id": "xyz"}
    h1 = request_hash(body)
    h2 = request_hash(body)
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex


def test_request_hash_key_order_independent():
    a = request_hash({"b": 2, "a": 1})
    b = request_hash({"a": 1, "b": 2})
    assert a == b


def test_request_hash_sensitive_to_values():
    assert request_hash({"a": 1}) != request_hash({"a": 2})
