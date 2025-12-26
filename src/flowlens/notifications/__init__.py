"""Notification system for FlowLens.

Supports email, webhook, Slack, Teams, and PagerDuty notifications for alerts and change events.
"""

from flowlens.notifications.base import NotificationChannel, NotificationManager
from flowlens.notifications.email import EmailChannel
from flowlens.notifications.webhook import WebhookChannel
from flowlens.notifications.slack import SlackChannel, SlackSettings
from flowlens.notifications.teams import TeamsChannel, TeamsSettings
from flowlens.notifications.pagerduty import PagerDutyChannel, PagerDutySettings

__all__ = [
    "NotificationChannel",
    "NotificationManager",
    "EmailChannel",
    "WebhookChannel",
    "SlackChannel",
    "SlackSettings",
    "TeamsChannel",
    "TeamsSettings",
    "PagerDutyChannel",
    "PagerDutySettings",
]
