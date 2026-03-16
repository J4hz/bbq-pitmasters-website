from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="home"),
    path("chefs/<int:chef_id>/", views.chef_detail, name="chef_detail"),
    path("checkout/<int:chef_id>/", views.checkout, name="checkout"),
    path("ticket/<int:order_id>/", views.ticket_confirmation, name="ticket_confirmation"),
    path("mpesa/callback/", views.mpesa_callback, name="mpesa_callback"),
]
