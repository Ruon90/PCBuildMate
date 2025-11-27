from django.db import models
from django.contrib.auth.models import User

## Create your models here.
class CPU(models.Model):
    brand = models.CharField(max_length=100)
    name = models.CharField(max_length=200)  # Model name
    socket = models.CharField(max_length=50)
    benchmark = models.FloatField()
    power_consumption = models.IntegerField(null=True, blank=True)  # watts
    msrp = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    live_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    live_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    image_url = models.URLField(max_length=500, null=True, blank=True)

    def __str__(self):
        return f"{self.brand} {self.name}"


class GPU(models.Model):
    brand = models.CharField(max_length=100)
    name = models.CharField(max_length=200)
    benchmark = models.FloatField()
    power_consumption = models.IntegerField(null=True, blank=True)
    msrp = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    live_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    live_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    image_url = models.URLField(max_length=500, null=True, blank=True)
    userbenchmark_url = models.URLField(max_length=500, null=True, blank=True)
    def __str__(self):
        return f"{self.brand} {self.name}"


class RAM(models.Model):
    brand = models.CharField(max_length=100)
    name = models.CharField(max_length=200)
    type = models.CharField(max_length=50)  # e.g., DDR4, DDR5
    benchmark = models.FloatField()
    power_consumption = models.IntegerField(null=True, blank=True)
    msrp = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    live_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    live_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    image_url = models.URLField(max_length=500, null=True, blank=True)

    def __str__(self):
        return f"{self.brand} {self.name}"


class Storage(models.Model):
    brand = models.CharField(max_length=100)
    name = models.CharField(max_length=200)
    interface = models.CharField(max_length=50)  # e.g., NVMe, SATA
    benchmark = models.FloatField()
    power_consumption = models.IntegerField(null=True, blank=True)
    msrp = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    live_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    live_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    image_url = models.URLField(max_length=500, null=True, blank=True)

    def __str__(self):
        return f"{self.brand} {self.name}"


class PSU(models.Model):
    brand = models.CharField(max_length=100)
    name = models.CharField(max_length=200)
    wattage = models.IntegerField()  # total PSU capacity
    benchmark = models.FloatField()
    msrp = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    live_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    live_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    image_url = models.URLField(max_length=500, null=True, blank=True)

    def __str__(self):
        return f"{self.brand} {self.name}"


class Motherboard(models.Model):
    brand = models.CharField(max_length=100)
    name = models.CharField(max_length=200)
    socket = models.CharField(max_length=50)
    ram_type = models.CharField(max_length=50)  # DDR4, DDR5
    benchmark = models.FloatField()
    msrp = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    live_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    live_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    image_url = models.URLField(max_length=500, null=True, blank=True)

    def __str__(self):
        return f"{self.brand} {self.name}"


class UserBuild(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    budget = models.DecimalField(max_digits=10, decimal_places=2)
    cpu = models.ForeignKey(CPU, on_delete=models.SET_NULL, null=True, blank=True)
    gpu = models.ForeignKey(GPU, on_delete=models.SET_NULL, null=True, blank=True)
    ram = models.ForeignKey(RAM, on_delete=models.SET_NULL, null=True, blank=True)
    psu = models.ForeignKey(PSU, on_delete=models.SET_NULL, null=True, blank=True)
    storage = models.ForeignKey(Storage, on_delete=models.SET_NULL, null=True, blank=True)
    motherboard = models.ForeignKey(Motherboard, on_delete=models.SET_NULL, null=True, blank=True)

    def total_price_range(self):
        parts = [self.cpu, self.gpu, self.ram, self.psu, self.storage, self.motherboard]
        min_total = sum([p.live_min for p in parts if p and p.live_min])
        max_total = sum([p.live_max for p in parts if p and p.live_max])
        return min_total, max_total

    def __str__(self):
        return f"Build for {self.user.username} (Budget: {self.budget})"
