"""Notification system for FlowLens.

Supports email notifications for alerts and change events.
"""

from flowlens.notifications.base import NotificationChannel, NotificationManager
from flowlens.notifications.email import EmailChannel

__all__ = [
    "NotificationChannel",
    "NotificationManager",
    "EmailChannel",
]
