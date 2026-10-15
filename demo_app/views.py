import json
import logging
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger("django.request")

def health_check(request):
    """Normal healthy endpoint for testing."""
    return JsonResponse({"status": "ok", "service": "django-ecommerce-backend"})

@csrf_exempt
def checkout_view(request):
    """
    Bug 1: KeyError.
    Simulates a payload missing the 'payment_method' key.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        data = {}

    cart_id = data.get("cart_id", 101)
    # BUG: Direct dictionary access without check or .get()
    payment_method = data["payment_method"]
    
    return JsonResponse({
        "status": "success",
        "cart_id": cart_id,
        "payment_method": payment_method
    })

def calculate_discount_view(request):
    """
    Bug 2: ZeroDivisionError.
    Simulates discount distribution across 0 items.
    """
    total_discount = float(request.GET.get("discount", 50.0))
    items_count = int(request.GET.get("items", 0))
    
    # BUG: No guard against zero items count
    discount_per_item = total_discount / items_count
    
    return JsonResponse({
        "total_discount": total_discount,
        "items_count": items_count,
        "discount_per_item": discount_per_item
    })

def user_profile_view(request):
    """
    Bug 3: AttributeError / NoneType.
    Simulates finding a user record that is None and accessing attributes.
    """
    user_id = request.GET.get("user_id")
    
    # Simulate DB lookup returning None
    user_record = None
    if user_id == "admin":
        user_record = {"username": "admin", "email": "admin@example.com"}
    
    if user_record is None:
        raise Http404(f"User with id '{user_id}' not found")
    
    email = user_record["email"] if isinstance(user_record, dict) else user_record.email
    
    return JsonResponse({"user_id": user_id, "email": email})

def manual_logger_error_view(request):
    """
    Bug 4: Explicit logger.error with traceback.
    Simulates caught or non-fatal exception logged via logger.error.
    """
    try:
        raise ConnectionResetError("Remote payment gateway (Stripe/PayPal) reset connection unexpectedly")
    except Exception as exc:
        logger.error(
            f"External service failure during checkout webhook: {exc}",
            exc_info=True,
            extra={"request_path": request.path, "service": "payment-gateway"}
        )
        return JsonResponse({"status": "handled_with_error_logged"}, status=502)
