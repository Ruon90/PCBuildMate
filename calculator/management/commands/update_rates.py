import os

import requests
from django.core.management.base import BaseCommand

from calculator.models import CurrencyRate

API_KEY = os.environ.get("EXCHANGE_RATE_API_KEY")
API_URL = f"https://v6.exchangerate-api.com/v6/{API_KEY}/latest/USD"


class Command(BaseCommand):
    help = "Update currency rates from ExchangeRate API (base USD)"

    def handle(self, *args, **kwargs):
        response = requests.get(API_URL)
        data = response.json()

        if data.get("result") != "success":
            self.stderr.write("Failed to fetch rates")
            return

        rates = data["conversion_rates"]
        for currency, rate in rates.items():
            CurrencyRate.objects.update_or_create(
                currency=currency, defaults={"rate_to_usd": rate}
            )
        self.stdout.write(
            self.style.SUCCESS("Currency rates updated successfully")
        )
