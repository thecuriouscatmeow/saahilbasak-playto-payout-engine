import hashlib
import json
from decimal import Decimal


def paise_to_rupees(paise: int) -> Decimal:
    return Decimal(paise) / Decimal(100)


def rupees_to_paise(rupees: "str | Decimal") -> int:
    return int(Decimal(str(rupees)) * 100)


def format_inr(paise: int) -> str:
    rupees = Decimal(paise) / Decimal(100)
    whole, frac = divmod(int(rupees * 100), 100)
    # Indian grouping: last 3 digits, then groups of 2
    s = str(whole)
    if len(s) <= 3:
        return f"₹{s}.{frac:02d}"
    result = s[-3:]
    s = s[:-3]
    while s:
        result = s[-2:] + "," + result
        s = s[:-2]
    return f"₹{result}.{frac:02d}"


def request_hash(body: dict) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
