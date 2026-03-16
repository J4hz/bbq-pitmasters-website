from __future__ import annotations

from typing import Any

import io
import logging

import qrcode
from django.conf import settings
from django.core.mail import EmailMessage

from .models import Order

logger = logging.getLogger(__name__)


def _generate_qr_png(order: Order) -> bytes:
    payload = (
        f"BBQ PITMASTERS | Order #{order.pk} | "
        f"PitMaster: {order.chef.name} | Pit name: {order.guest_name}"
    )
    qr = qrcode.make(payload)
    buffer = io.BytesIO()
    qr.save(buffer, format="PNG")
    return buffer.getvalue()


def _send_ticket_email(order: Order, qr_png: bytes) -> None:
    subject = f"Your BBQ PITMASTERS Ticket #{order.pk}"
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com")
    to = [order.guest_email]

    body_lines = [
        "Thank you for booking a BBQ PITMASTERS experience.",
        "",
        f"PitMaster: {order.chef.name}",
        f"Pit name: {order.guest_name}",
        f"Order ID: {order.pk}",
        "",
        "Your scannable ticket is attached as a QR code image.",
        "Present it on your phone or printed at the entrance.",
    ]
    body = "\n".join(body_lines)

    email = EmailMessage(subject, body, from_email, to)
    email.attach(f"ticket-{order.pk}.png", qr_png, "image/png")
    try:
        email.send(fail_silently=False)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Failed to send ticket email for order %s: %s", order.pk, exc)


def _send_ticket_sms(order: Order, qr_png: bytes) -> None:
    # Placeholder: integrate your preferred SMS/WhatsApp provider here.
    # Many providers accept media URLs rather than raw bytes; you may need to
    # upload `qr_png` to object storage (e.g. S3, Cloudinary) and send the URL.
    logger.info("Ticket SMS sending not configured for order %s", order.pk)


def send_ticket_notifications(order: Order) -> dict[str, Any]:
    qr_png = _generate_qr_png(order)
    _send_ticket_email(order, qr_png)
    _send_ticket_sms(order, qr_png)
    return {"status": "sent"}
