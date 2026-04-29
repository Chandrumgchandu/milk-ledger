from decimal import Decimal

from app.utils.helpers import money


def compute_amount(liters, rate):
    return money(Decimal(liters) * Decimal(rate))
