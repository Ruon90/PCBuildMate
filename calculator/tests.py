from django.test import TestCase

from calculator.models import (
    CPU,
    GPU,
    PSU,
    RAM,
    Case,
    CPUCooler,
    Motherboard,
    Storage,
)
from calculator.services import build_calculator


class TestCalculator(TestCase):
    def setUp(self):
        self.cpu = CPU(
            socket="AM4",
            price=200,
            userbenchmark_score=100,
            blender_score=80,
            power_consumption_overclocked=95,
        )
        self.gpu = GPU(
            price=300, userbenchmark_score=150, blender_score=120, tdp=200
        )
        self.mobo = Motherboard(
            socket="AM4",
            price=100,
            ddr_version="DDR4",
            ddr_max_speed=3200,
            nvme_support="True",
            form_factor="ATX",
        )
        self.ram = RAM(
            price=80, ddr_generation="DDR4", frequency_mhz=3000, benchmark=50
        )
        self.storage = Storage(price=60, interface="nvme")
        self.psu = PSU(price=90, wattage=600)
        self.cooler = CPUCooler(price=50, power_throughput=120)
        self.case = Case(price=70, case_type="ATX")

    def test_find_best_build_under_budget(self):
        best, progress = build_calculator.find_best_build(
            budget=1000,
            mode="gaming",
            resolution="1080p",
            cpus=[self.cpu],
            gpus=[self.gpu],
            mobos=[self.mobo],
            rams=[self.ram],
            storages=[self.storage],
            psus=[self.psu],
            coolers=[self.cooler],
            cases=[self.case],
        )
        self.assertIsNotNone(best)
        self.assertLessEqual(best.total_price, 1000)
