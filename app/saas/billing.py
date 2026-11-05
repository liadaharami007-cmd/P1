"""ממשק לספק תשלומים עתידי (למשל Stripe / Paddle / Tranzila).

כרגע אין ספק מחובר: אין גבייה, ושינוי מסלול אפשרי רק ע"י מנהל הפלטפורמה.
כדי לחבר ספק: לממש BillingProvider, ולהחליף את get_provider(). ה-webhook של הספק יעדכן
accounts.plan / subscription_status / billing_customer_id.
"""
from __future__ import annotations

from typing import Protocol


class BillingProvider(Protocol):
    name: str

    def configured(self) -> bool: ...
    def create_checkout_url(self, account_id: str, plan: str) -> str: ...
    def customer_portal_url(self, account_id: str) -> str: ...


class NotConfigured:
    name = "none"

    def configured(self) -> bool:
        return False

    def create_checkout_url(self, account_id: str, plan: str) -> str:
        raise RuntimeError("ספק תשלומים לא מחובר")

    def customer_portal_url(self, account_id: str) -> str:
        raise RuntimeError("ספק תשלומים לא מחובר")


def get_provider() -> BillingProvider:
    return NotConfigured()
