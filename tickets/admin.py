from django.contrib import admin
from django.db.models import Count

from .models import Chef, Order


@admin.register(Chef)
class ChefAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "mpesa_till_number",
        "paybill_number",
        "event_datetime",
        "ticket_price",
        "ticket_capacity",
        "remaining_tickets",
    )
    search_fields = ("name",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "chef",
        "guest_name",
        "guest_email",
        "status",
        "created_at",
    )
    list_filter = ("status", "chef")
    search_fields = ("guest_name", "guest_email", "transaction_id")
    date_hierarchy = "created_at"

    def changelist_view(self, request, extra_context=None):  # type: ignore[override]
        # Simple sales dashboard for paid orders by chef.
        qs = Order.objects.filter(status=Order.STATUS_PAID)
        summary = (
            qs.values("chef__name")
            .annotate(total_paid=Count("id"))
            .order_by("chef__name")
        )
        extra_context = extra_context or {}
        extra_context["sales_summary"] = summary
        return super().changelist_view(request, extra_context=extra_context)
