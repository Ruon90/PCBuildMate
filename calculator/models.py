from django.db import models
from django.contrib.auth.models import User

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
