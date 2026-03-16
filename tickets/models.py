from django.db import models
from django.db.models import Sum


class Chef(models.Model):
    name = models.CharField(max_length=255)
    bio = models.TextField()
    about = models.TextField(blank=True)
    image = models.ImageField(upload_to="chefs/", blank=True, null=True)
    menu_description = models.TextField()
    mpesa_till_number = models.CharField(max_length=50)
    paybill_number = models.CharField(max_length=50, blank=True)
    event_datetime = models.DateTimeField(blank=True, null=True)
    ticket_capacity = models.PositiveIntegerField(blank=True, null=True)
    ticket_price = models.PositiveIntegerField(blank=True, null=True, help_text="Ticket price in KES")

    def __str__(self) -> str:
        return self.name

    def remaining_tickets(self):
        if self.ticket_capacity is None:
            return None
        agg = self.orders.filter(
            status__in=[Order.STATUS_PENDING, Order.STATUS_PAID]
        ).aggregate(total=Sum("quantity"))
        sold = agg["total"] or 0
        remaining = self.ticket_capacity - sold
        return max(remaining, 0)


class Order(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PAID = "paid"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PAID, "Paid"),
    ]

    chef = models.ForeignKey(Chef, on_delete=models.CASCADE, related_name="orders")
    quantity = models.PositiveIntegerField(default=1)
    guest_name = models.CharField(max_length=255)
    guest_email = models.EmailField()
    guest_phone = models.CharField(max_length=30)
    transaction_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Order #{self.pk} - {self.guest_name}"
