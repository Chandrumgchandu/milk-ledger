from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from flask_login import UserMixin
from werkzeug.security import check_password_hash


def _to_decimal(value):
    if value in (None, ""):
        return None
    return Decimal(str(value))


def _to_date(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(value) if value else None


def _to_datetime(value):
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


@dataclass
class Admin(UserMixin):
    id: int
    name: str
    phone: str
    password_hash: str
    created_at: datetime | None = None

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @classmethod
    def from_dict(cls, row):
        return cls(int(row["id"]), row["name"], row["phone"], row["password_hash"], _to_datetime(row.get("created_at")))


@dataclass
class Farmer:
    id: int
    unique_code: int
    name: str
    phone: str
    village: str | None = None
    is_active: bool = True
    created_at: datetime | None = None

    @classmethod
    def from_dict(cls, row):
        return cls(
            int(row["id"]),
            int(row["unique_code"]),
            row["name"],
            row["phone"],
            row.get("village"),
            bool(row.get("is_active", True)),
            _to_datetime(row.get("created_at")),
        )


@dataclass
class MilkEntry:
    id: int
    farmer_id: int
    date: date
    session: str
    quantity: Decimal
    rate: Decimal
    amount: Decimal
    created_at: datetime | None = None
    updated_at: datetime | None = None
    farmer: Farmer | None = None

    @classmethod
    def from_dict(cls, row):
        return cls(
            int(row["id"]),
            int(row["farmer_id"]),
            _to_date(row["date"]),
            row["session"],
            _to_decimal(row["quantity"]),
            _to_decimal(row["rate"]),
            _to_decimal(row["amount"]),
            _to_datetime(row.get("created_at")),
            _to_datetime(row.get("updated_at")),
        )


@dataclass
class Rate:
    id: int
    rate: Decimal
    effective_from: datetime
    created_by: str

    @classmethod
    def from_dict(cls, row):
        return cls(int(row["id"]), _to_decimal(row["rate"]), _to_datetime(row["effective_from"]), row.get("created_by", "system"))


@dataclass
class Payment:
    id: int
    farmer_id: int
    amount_paid: Decimal
    payment_date: date
    note: str | None = None
    created_at: datetime | None = None
    farmer: Farmer | None = None

    @classmethod
    def from_dict(cls, row):
        return cls(
            int(row["id"]),
            int(row["farmer_id"]),
            _to_decimal(row["amount_paid"]),
            _to_date(row["payment_date"]),
            row.get("note"),
            _to_datetime(row.get("created_at")),
        )


@dataclass
class StoreTransactionItem:
    id: int
    transaction_id: int
    item_name: str
    quantity: Decimal
    unit: str | None = None
    unit_price: Decimal | None = None
    subtotal: Decimal | None = None
    created_at: datetime | None = None

    @classmethod
    def from_dict(cls, row):
        return cls(
            int(row["id"]),
            int(row["transaction_id"]),
            row["item_name"],
            _to_decimal(row.get("quantity")),
            row.get("unit"),
            _to_decimal(row.get("unit_price")),
            _to_decimal(row.get("subtotal")),
            _to_datetime(row.get("created_at")),
        )


@dataclass
class StoreTransaction:
    id: int
    farmer_id: int
    bill_date: date
    total_amount: Decimal
    item_count: int = 0
    note: str | None = None
    entry_source: str | None = None
    duplicate_guard: str | None = None
    is_locked: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    farmer: Farmer | None = None
    items: list[StoreTransactionItem] = field(default_factory=list)

    @classmethod
    def from_dict(cls, row):
        return cls(
            int(row["id"]),
            int(row["farmer_id"]),
            _to_date(row["bill_date"]),
            _to_decimal(row["total_amount"]),
            int(row.get("item_count") or 0),
            row.get("note"),
            row.get("entry_source"),
            row.get("duplicate_guard"),
            bool(row.get("is_locked", False)),
            _to_datetime(row.get("created_at")),
            _to_datetime(row.get("updated_at")),
        )


@dataclass
class MonthlySettlement:
    id: int
    farmer_id: int
    settlement_month: date
    milk_total: Decimal
    store_credit_total: Decimal
    net_amount: Decimal
    status: str
    is_locked: bool = False
    settled_on: datetime | None = None
    note: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    farmer: Farmer | None = None

    @classmethod
    def from_dict(cls, row):
        return cls(
            int(row["id"]),
            int(row["farmer_id"]),
            _to_date(row["settlement_month"]),
            _to_decimal(row.get("milk_total")),
            _to_decimal(row.get("store_credit_total")),
            _to_decimal(row.get("net_amount")),
            row.get("status", "settled"),
            bool(row.get("is_locked", False)),
            _to_datetime(row.get("settled_on")),
            row.get("note"),
            _to_datetime(row.get("created_at")),
            _to_datetime(row.get("updated_at")),
        )


@dataclass
class PaymentLog:
    id: int
    farmer_id: int
    amount: Decimal
    payment_date: date
    direction: str
    settlement_id: int | None = None
    note: str | None = None
    created_at: datetime | None = None
    farmer: Farmer | None = None

    @classmethod
    def from_dict(cls, row):
        return cls(
            int(row["id"]),
            int(row["farmer_id"]),
            _to_decimal(row.get("amount")),
            _to_date(row["payment_date"]),
            row.get("direction", "to_farmer"),
            int(row["settlement_id"]) if row.get("settlement_id") else None,
            row.get("note"),
            _to_datetime(row.get("created_at")),
        )


@dataclass
class WhatsAppState:
    phone: str
    role: str
    state: str
    context_value: str | None = None
    last_entry_id: int | None = None
    last_farmer_id: int | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_dict(cls, row):
        return cls(
            row["phone"],
            row["role"],
            row["state"],
            row.get("context_value"),
            int(row["last_entry_id"]) if row.get("last_entry_id") else None,
            int(row["last_farmer_id"]) if row.get("last_farmer_id") else None,
            _to_datetime(row.get("updated_at")),
        )
