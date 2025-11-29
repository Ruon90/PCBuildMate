from django.db import models
from django.contrib.auth.models import User

# Core component models
class CPU(models.Model):
    name = models.CharField(max_length=100)
    brand = models.CharField(max_length=50)
    socket = models.CharField(max_length=50)
    tdp = models.IntegerField(null=True, blank=True)  # watts
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True) 

class GPU(models.Model):
    name = models.CharField(max_length=100)
    brand = models.CharField(max_length=50)
    vram_gb = models.IntegerField(null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True) 

class Motherboard(models.Model):
    name = models.CharField(max_length=100)
    brand = models.CharField(max_length=50)
    socket = models.CharField(max_length=50)
    chipset = models.CharField(max_length=50)
    form_factor = models.CharField(max_length=50)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True) 

class RAM(models.Model):
    name = models.CharField(max_length=100)
    capacity_gb = models.IntegerField()
    speed_mhz = models.IntegerField()
    type = models.CharField(max_length=20)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True) 

class Storage(models.Model):
    name = models.CharField(max_length=100)
    capacity_gb = models.IntegerField()
    type = models.CharField(max_length=20)  # SSD/HDD/NVMe
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True) 

class PSU(models.Model):
    name = models.CharField(max_length=100)
    wattage = models.IntegerField()
    efficiency_rating = models.CharField(max_length=20, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True) 

class Cooler(models.Model):
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=50)  # Air/Liquid
    socket_support = models.CharField(max_length=100)
    max_wattage = models.IntegerField(null=True, blank=True)  # AI-enriched
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True) 

class Case(models.Model):
    name = models.CharField(max_length=100)
    form_factor = models.CharField(max_length=50)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True) 

# Extended details for modal display
class ComponentDetail(models.Model):
    component_type = models.CharField(max_length=20)  # CPU/GPU/etc
    component_id = models.IntegerField()
    field_name = models.CharField(max_length=100)
    field_value = models.TextField()

# Benchmarks (CPU/GPU: Blender + UserBenchmark, RAM/Storage: UserBenchmark only)
class Benchmark(models.Model):
    component_type = models.CharField(
        max_length=20,
        choices=[
            ('CPU','CPU'),
            ('GPU','GPU'),
            ('RAM','RAM'),
            ('Storage','Storage'),
        ]
    )
    component_id = models.IntegerField()
    source = models.CharField(max_length=50)  # 'UserBenchmark' or 'Blender'
    score = models.FloatField()

# User builds
class UserBuild(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    cpu = models.ForeignKey(CPU, on_delete=models.SET_NULL, null=True)
    gpu = models.ForeignKey(GPU, on_delete=models.SET_NULL, null=True)
    motherboard = models.ForeignKey(Motherboard, on_delete=models.SET_NULL, null=True)
    ram = models.ForeignKey(RAM, on_delete=models.SET_NULL, null=True)
    storage = models.ForeignKey(Storage, on_delete=models.SET_NULL, null=True)
    psu = models.ForeignKey(PSU, on_delete=models.SET_NULL, null=True)
    cooler = models.ForeignKey(Cooler, on_delete=models.SET_NULL, null=True)
    case = models.ForeignKey(Case, on_delete=models.SET_NULL, null=True)
    budget = models.DecimalField(max_digits=10, decimal_places=2)
    mode = models.CharField(
        max_length=20,
        choices=[('gaming','Gaming'),('workstation','Workstation')]
    )
    created_at = models.DateTimeField(auto_now_add=True)
