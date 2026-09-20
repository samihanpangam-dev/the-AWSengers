"""Provider-agnostic development subscription state and access enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock

from .config import SUBSCRIPTION_PROVIDER, TRIAL_DAYS

PLAN_ID = "ai_agent"
PLAN_PRICE_INR = 99


@dataclass
class Subscription:
    user_id: str
    status: str
    trial_started_at: datetime
    current_period_end: datetime
    provider: str = SUBSCRIPTION_PROVIDER

    def as_dict(self) -> dict:
        return {
            "plan": PLAN_ID,
            "price_inr": PLAN_PRICE_INR,
            "interval": "month",
            "trial_days": TRIAL_DAYS,
            "status": self.status,
            "provider": self.provider,
            "trial_started_at": self.trial_started_at.isoformat(),
            "current_period_end": self.current_period_end.isoformat(),
            "can_use_agent": self.status in {"trialing", "active"},
        }


class SubscriptionStore:
    def __init__(self) -> None:
        self._items: dict[str, Subscription] = {}
        self._lock = RLock()

    def status(self, user_id: str) -> Subscription:
        now = datetime.now(timezone.utc)
        with self._lock:
            item = self._items.get(user_id)
            if item is None:
                item = Subscription(user_id, "trialing", now, now + timedelta(days=TRIAL_DAYS))
                self._items[user_id] = item
            elif item.status == "trialing" and now >= item.current_period_end:
                item.status = "expired"
            return item

    def activate(self, user_id: str) -> Subscription:
        with self._lock:
            item = self.status(user_id)
            item.status = "active"
            item.current_period_end = datetime.now(timezone.utc) + timedelta(days=30)
            return item

    def apply_webhook(self, user_id: str, event: str) -> Subscription:
        if event in {"subscription.active", "invoice.paid"}:
            return self.activate(user_id)
        item = self.status(user_id)
        if event in {"subscription.cancelled", "invoice.failed"}:
            item.status = "cancelled" if event.endswith("cancelled") else "past_due"
        return item

    def require_access(self, user_id: str) -> Subscription:
        item = self.status(user_id)
        if item.status not in {"trialing", "active"}:
            raise PermissionError("An active AI Agent subscription or trial is required")
        return item


subscription_store = SubscriptionStore()
