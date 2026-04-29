from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from apps.merchants.models import Merchant


class MerchantApiKeyAuthentication(BaseAuthentication):
    """Authenticates via `Authorization: Bearer <merchant-api-key>`.

    Returns (merchant, merchant_id_str) on success so views can read
    the server-side merchant identity from request.auth instead of
    trusting a caller-supplied header.
    """

    def authenticate(self, request):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        api_key = auth[7:]
        try:
            merchant = Merchant.objects.get(api_key=api_key)
        except (Merchant.DoesNotExist, ValueError):
            raise AuthenticationFailed("Invalid API key.")
        return (merchant, str(merchant.id))
