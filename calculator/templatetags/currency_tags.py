from decimal import Decimal, InvalidOperation

from django import template

from ..models import CurrencyRate

register = template.Library()


@register.filter
def currency_symbol(code):
    """Return a currency symbol for an ISO code. Fallback to '$'."""
    if not code:
        return "$"
    code = str(code).upper()
    mapping = {
        "USD": "$",
        "GBP": "£",
        "EUR": "€",
    }
    return mapping.get(code, code)


@register.filter
def convert_from_usd(amount, currency_code):
    """
    Convert an amount in USD to the given currency code.

    Uses CurrencyRate.rate_to_usd for conversion.

    amount: numeric or string representing USD amount
    currency_code: ISO code to convert to (e.g., 'EUR').

    Returns a Decimal rounded to 2 decimal places; on error returns the
    original amount.
    """
    try:
        amt = Decimal(amount)
    except (InvalidOperation, TypeError, ValueError):
        return amount

    code = currency_code or "USD"

    # Cache currency rates in-process to avoid a DB query per template call.
    # Rates are small and updated occasionally via management command, so
    # a simple module-level cache is sufficient for the dev server.
    if not hasattr(convert_from_usd, "_rate_cache"):
        try:
            cache = {}
            for r in CurrencyRate.objects.all():
                try:
                    cache[str(r.currency).upper()] = Decimal(r.rate_to_usd)
                except Exception:
                    continue
            setattr(convert_from_usd, "_rate_cache", cache)
        except Exception:
            setattr(convert_from_usd, "_rate_cache", {})

    rate_cache = getattr(convert_from_usd, "_rate_cache", {})
    rate = rate_cache.get(str(code).upper())

    # If no cached rate found, assume USD (no conversion)
    if not rate:
        return amt.quantize(Decimal("0.01"))

    try:
        if rate == 0:
            return amt.quantize(Decimal("0.01"))
        converted = (amt / rate).quantize(Decimal("0.01"))
        return converted
    except Exception:
        return amt.quantize(Decimal("0.01"))
