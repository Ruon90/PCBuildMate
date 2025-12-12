from django.test import TestCase
from django.urls import reverse

from .models import CPU, GPU, PSU, RAM, Case, CPUCooler, Motherboard, Storage


class AlternativesViewTests(TestCase):
    def setUp(self):
        # create minimal components
        self.cpu = CPU.objects.create(name="Test CPU", socket="AM4", price=200)
        self.gpu = GPU.objects.create(gpu_name="Test GPU", price=300)
        self.mobo = Motherboard.objects.create(
            name="Test Mobo", socket="AM4", price=120
        )
        self.ram = RAM.objects.create(
            name="Test RAM", ddr_generation="DDR4", price=80
        )
        self.storage = Storage.objects.create(
            name="Test NVMe", interface="nvme", price=60
        )
        self.psu = PSU.objects.create(name="Test PSU", wattage=650, price=90)
        self.cooler = CPUCooler.objects.create(
            name="Test Cooler", power_throughput=150, price=50
        )
        self.case = Case.objects.create(
            name="Test Case", case_type="ATX", price=70
        )

        # prepare a sample alternative (as stored in session by the view)
        self.alt = {
            "cpu": self.cpu.id,
            "gpu": self.gpu.id,
            "motherboard": self.mobo.id,
            "ram": self.ram.id,
            "storage": self.storage.id,
            "psu": self.psu.id,
            "cooler": self.cooler.id,
            "case": self.case.id,
            "price": 870.0,
            "score": 123.4,
            "bottleneck_type": "CPU",
            "bottleneck_pct": 12.5,
            "fps": {"Cyberpunk 2077": {"overall": 60, "cpu": 70, "gpu": 65}},
        }

    def test_alternatives_page_shows_cards(self):
        session = self.client.session
        session["preview_alternatives"] = [self.alt]
        session["preview_build"] = {}
        session.save()

        resp = self.client.get(reverse("alternatives"))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("Alt #1", content)
        self.assertIn("Test CPU", content)
        self.assertIn("Test GPU", content)
        self.assertIn("CPU", content)  # bottleneck text

    def test_select_alternative_replaces_preview(self):
        session = self.client.session
        session["preview_alternatives"] = [self.alt]
        session["preview_build"] = {
            "budget": 1000,
            "currency": "USD",
            "mode": "gaming",
            "resolution": "1440p",
        }
        session.save()

        resp = self.client.post(
            reverse("select_alternative"), {"alt_index": 0}, follow=True
        )
        self.assertEqual(resp.status_code, 200)
        new_preview = self.client.session.get("preview_build")
        self.assertIsNotNone(new_preview)
        self.assertEqual(new_preview["cpu"], self.cpu.id)
        self.assertEqual(new_preview["gpu"], self.gpu.id)
        # alternatives should still be present until save
        self.assertIn("preview_alternatives", self.client.session)
