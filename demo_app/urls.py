from django.urls import path
from . import views

urlpatterns = [
    path("health/", views.health_check, name="health_check"),
    path("api/checkout/", views.checkout_view, name="checkout"),
    path("api/calculate-discount/", views.calculate_discount_view, name="calculate_discount"),
    path("api/user-profile/", views.user_profile_view, name="user_profile"),
    path("api/manual-error/", views.manual_logger_error_view, name="manual_error"),
]
