from __future__ import annotations

from typing import Any

import base64
import datetime as dt
import logging

import requests
from django.conf import settings

from .models import Order

logger = logging.getLogger(__name__)


def _get_base_url() -> str:
    """Return the Daraja base URL (sandbox or live).

    Configure via MPESA_BASE_URL or MPESA_ENVIRONMENT. Defaults to sandbox.
    """

    explicit = getattr(settings, "MPESA_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")

    env = getattr(settings, "MPESA_ENVIRONMENT", "sandbox").lower()
    if env == "live":
        return "https://api.safaricom.co.ke"
    return "https://sandbox.safaricom.co.ke"


def _get_access_token(base_url: str) -> str:
    """Fetch an OAuth access token from Daraja.

    Requires MPESA_CONSUMER_KEY and MPESA_CONSUMER_SECRET in settings/env.
    """

    consumer_key = getattr(settings, "MPESA_CONSUMER_KEY", None)
    consumer_secret = getattr(settings, "MPESA_CONSUMER_SECRET", None)
    if not consumer_key or not consumer_secret:
        raise RuntimeError("MPESA_CONSUMER_KEY/SECRET are not configured")

    token_url = f"{base_url}/oauth/v1/generate?grant_type=client_credentials"
    resp = requests.get(token_url, auth=(consumer_key, consumer_secret), timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data.get("access_token") or ""


def initiate_stk_push(order: Order) -> dict[str, Any]:
    """Initiate an M-Pesa STK push for the given order via Daraja.

    Routing logic:
    - Pull the PitMaster's specific Till/Shortcode from the database
      (``order.chef.mpesa_till_number``).
    - Use it as the BusinessShortCode / PartyB so that each PitMaster receives
      funds to their own destination.

    Configuration (set via Django settings or env vars):
    - MPESA_CONSUMER_KEY / MPESA_CONSUMER_SECRET
    - MPESA_PASS_KEY
    - MPESA_CALLBACK_URL
    - MPESA_ENVIRONMENT ("sandbox" or "live") or MPESA_BASE_URL

    The Amount is taken from ``order.chef.ticket_price`` (in KES). If no price
    is configured, this function falls back to MPESA_TICKET_AMOUNT or 1.
    """

    chef = order.chef
    # Prefer a configured PayBill number, fall back to Till/Buy-Goods shortcode,
    # then to a global BusinessShortCode from settings.
    shortcode = (
        getattr(chef, "paybill_number", "")
        or chef.mpesa_till_number
        or getattr(settings, "MPESA_BUSINESS_SHORT_CODE", "")
    )

    base_url = _get_base_url()
    business_shortcode = shortcode
    pass_key = getattr(settings, "MPESA_PASS_KEY", "")
    callback_url = getattr(
        settings,
        "MPESA_CALLBACK_URL",
        "https://example.com/mpesa/callback/",
    )

    # Derive ticket amount: PitMaster-specific price (KES) * quantity -> integer amount.
    unit_price = chef.ticket_price or getattr(settings, "MPESA_TICKET_AMOUNT", 1)
    quantity = getattr(order, "quantity", 1) or 1
    amount = int(unit_price) * int(quantity)

    # Timestamp and password per Daraja spec.
    timestamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")
    pw_raw = f"{business_shortcode}{pass_key}{timestamp}".encode("utf-8")
    password = base64.b64encode(pw_raw).decode("utf-8")

    try:
        access_token = _get_access_token(base_url)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Failed to obtain M-Pesa access token: %s", exc)
        return {"error": "access_token_error", "detail": str(exc)}

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    stk_url = f"{base_url}/mpesa/stkpush/v1/processrequest"

    payload = {
        "BusinessShortCode": business_shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": getattr(
            settings,
            "MPESA_TRANSACTION_TYPE",
            "CustomerBuyGoodsOnline",
        ),
        "Amount": int(amount),
        "PartyA": order.guest_phone,
        "PartyB": business_shortcode,
        "PhoneNumber": order.guest_phone,
        "CallBackURL": callback_url,
        "AccountReference": f"BBQ-{order.pk}",
        "TransactionDesc": f"BBQ PITMASTERS ticket for {chef.name}",
    }

    try:
        resp = requests.post(stk_url, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("M-Pesa STK push failed: %s", exc)
        return {"error": "stk_push_error", "detail": str(exc), "payload": payload}

    checkout_request_id = data.get("CheckoutRequestID")
    if checkout_request_id and not order.transaction_id:
        order.transaction_id = checkout_request_id
        order.save(update_fields=["transaction_id"])

    return {"response": data, "payload": payload}
