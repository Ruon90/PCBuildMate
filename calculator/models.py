from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
# Import the hardware models from the app where you defined them
from hardware.models import CPU, GPU, Motherboard, RAM, Storage, PSU, CPUCooler, Case, ThermalPaste


class UserBuild(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    cpu = models.ForeignKey(CPU, on_delete=models.SET_NULL, null=True)
    gpu = models.ForeignKey(GPU, on_delete=models.SET_NULL, null=True)
    motherboard = models.ForeignKey(Motherboard, on_delete=models.SET_NULL, null=True)
    ram = models.ForeignKey(RAM, on_delete=models.SET_NULL, null=True)
    storage = models.ForeignKey(Storage, on_delete=models.SET_NULL, null=True)
    psu = models.ForeignKey(PSU, on_delete=models.SET_NULL, null=True)
    cooler = models.ForeignKey(CPUCooler, on_delete=models.SET_NULL, null=True)  # fixed
    case = models.ForeignKey(Case, on_delete=models.SET_NULL, null=True)
    budget = models.DecimalField(max_digits=10, decimal_places=2)
    mode = models.CharField(
        max_length=20,
        choices=[('gaming','Gaming'),('workstation','Workstation')]
    )
    thermal_paste = models.ForeignKey(ThermalPaste, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_score = models.IntegerField(default=0)
    # ISO currency code for the user's selected currency when saving a build
    currency = models.CharField(max_length=3, default="USD")

    def calculate_totals(self):
        # Keep weights as floats for simplicity
        weights = {
            "userbenchmark": 0.6,
            "blender": 0.4,
        }

        # Prices: always Decimal
        price = Decimal("0.00")
        if self.cpu and self.cpu.price:
            price += self.cpu.price
        if self.gpu and self.gpu.price:
            price += self.gpu.price
        if self.ram and self.ram.price:
            price += self.ram.price
        # add other components...

        # Scores: cast to float before multiplying
        ub_score = float(self.cpu.userbenchmark_score or 0)
        blender_score = float(self.cpu.blender_score or 0)

        score = int(
            ub_score * weights["userbenchmark"] +
            blender_score * weights["blender"]
        )

        return price, score

    def save(self, *args, **kwargs):
        self.total_price, self.total_score = self.calculate_totals()
        super().save(*args, **kwargs)


    @property
    def live_total_price(self):
        """Always fresh calculation (ignores cached field)."""
        return self.calculate_totals()[0]

    @property
    def live_total_score(self):
        """Always fresh calculation (ignores cached field)."""
        return self.calculate_totals()[1]

class CurrencyRate(models.Model):
    currency = models.CharField(max_length=3, unique=True)
    rate_to_usd = models.DecimalField(max_digits=12, decimal_places=6)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.currency}: {self.rate_to_usd}"
