from __future__ import annotations

import json

from django.db.models import Sum
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from .forms import GuestCheckoutForm
from .models import Chef, Order
from .mpesa_handler import initiate_stk_push
from .ticket_notifications import send_ticket_notifications


def index(request: HttpRequest) -> HttpResponse:
    chefs = Chef.objects.all()
    event_datetime_iso = "2026-03-01T17:00:00+03:00"
    main_event_video_url = ""
    return render(
        request,
        "tickets/index.html",
        {
            "chefs": chefs,
            "event_datetime_iso": event_datetime_iso,
            "main_event_video_url": main_event_video_url,
        },
    )


def chef_detail(request: HttpRequest, chef_id: int) -> HttpResponse:
    chef = get_object_or_404(Chef, pk=chef_id)
    event_datetime_iso = None
    if chef.event_datetime is not None:
        event_datetime_iso = chef.event_datetime.isoformat()

    total_capacity = chef.ticket_capacity
    remaining_capacity = None
    if total_capacity is not None:
        agg = chef.orders.filter(
            status__in=[Order.STATUS_PENDING, Order.STATUS_PAID]
        ).aggregate(total=Sum("quantity"))
        sold = agg["total"] or 0
        remaining_capacity = max(total_capacity - sold, 0)

    return render(
        request,
        "tickets/chef_detail.html",
        {
            "chef": chef,
            "event_datetime_iso": event_datetime_iso,
            "total_capacity": total_capacity,
            "remaining_capacity": remaining_capacity,
        },
    )


def checkout(request: HttpRequest, chef_id: int) -> HttpResponse:
    chef = get_object_or_404(Chef, pk=chef_id)

    capacity = chef.ticket_capacity
    agg = chef.orders.filter(
        status__in=[Order.STATUS_PENDING, Order.STATUS_PAID]
    ).aggregate(total=Sum("quantity"))
    sold_quantity = agg["total"] or 0
    remaining = None
    if capacity is not None:
        remaining = max(capacity - sold_quantity, 0)
    sold_out = capacity is not None and remaining is not None and remaining <= 0

    if request.method == "POST":
        form = GuestCheckoutForm(request.POST)
        if form.is_valid():
            qty = form.cleaned_data.get("quantity", 1)
            if capacity is not None and remaining is not None and qty > remaining:
                form.add_error(
                    "quantity",
                    f"Only {remaining} tickets are left for this PitMaster.",
                )
            elif sold_out:
                form.add_error(
                    None,
                    "Tickets for this PitMaster are sold out.",
                )
            else:
                # Enforce per-phone ticket cap (max 5 tickets per PitMaster per phone).
                phone = form.cleaned_data.get("guest_phone")
                phone_limit = 5
                phone_agg = chef.orders.filter(
                    guest_phone=phone,
                    status__in=[Order.STATUS_PENDING, Order.STATUS_PAID],
                ).aggregate(total=Sum("quantity"))
                already_have = phone_agg["total"] or 0

                if already_have + qty > phone_limit:
                    remaining_allowed = max(phone_limit - already_have, 0)
                    if remaining_allowed > 0:
                        msg = (
                            f"This phone number can only hold {phone_limit} tickets "
                            f"for this PitMaster. You may purchase {remaining_allowed} more."
                        )
                    else:
                        msg = (
                            f"This phone number has already reached the limit of "
                            f"{phone_limit} tickets for this PitMaster."
                        )
                    form.add_error("guest_phone", msg)
                else:
                    order: Order = form.save(commit=False)
                    order.chef = chef
                    order.save()

                    initiate_stk_push(order)

                    return redirect("ticket_confirmation", order_id=order.pk)
    else:
        form = GuestCheckoutForm()

    return render(
        request,
        "tickets/checkout.html",
        {"chef": chef, "form": form, "sold_out": sold_out, "remaining": remaining},
    )
def ticket_confirmation(request: HttpRequest, order_id: int) -> HttpResponse:
    order = get_object_or_404(Order, pk=order_id)
    return render(
        request,
        "tickets/ticket_confirmation.html",
        {"order": order},
    )


@csrf_exempt
def mpesa_callback(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")

    transaction_id = payload.get("transaction_id") or payload.get("CheckoutRequestID")
    result_code = payload.get("ResultCode", 0)

    if not transaction_id:
        return HttpResponseBadRequest("Missing transaction_id")

    try:
        order = Order.objects.get(transaction_id=transaction_id)
    except Order.DoesNotExist:
        return HttpResponseBadRequest("Order not found")

    was_paid = order.status == Order.STATUS_PAID
    if str(result_code) == "0":
        if not was_paid:
            order.status = Order.STATUS_PAID
            order.save(update_fields=["status"])
            send_ticket_notifications(order)

    return JsonResponse({"status": "ok"})
