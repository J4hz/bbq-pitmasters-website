from django import forms

from .models import Order


class GuestCheckoutForm(forms.ModelForm):
    quantity = forms.IntegerField(
        min_value=1,
        max_value=10,
        initial=1,
        label="Number of tickets",
    )

    class Meta:
        model = Order
        fields = ["guest_name", "guest_email", "guest_phone", "quantity"]
