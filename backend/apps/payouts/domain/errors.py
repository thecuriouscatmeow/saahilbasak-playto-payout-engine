from dataclasses import dataclass


@dataclass
class InvalidStateTransition(Exception):
    frm: str
    to: str

    def __str__(self):
        return f"Illegal transition {self.frm!r} → {self.to!r}"


@dataclass
class InsufficientBalance(Exception):
    merchant_id: str
    requested_paise: int
    available_paise: int


@dataclass
class IdempotencyPayloadMismatch(Exception):
    idempotency_key: str


@dataclass
class IdempotencyInFlight(Exception):
    idempotency_key: str
    payout_id: str


@dataclass
class BankAccountNotFound(Exception):
    account_id: str
