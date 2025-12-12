from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from .models import UserBuild, CPU, GPU, PSU, RAM, Case, CPUCooler, Motherboard, Storage


class SecurityTests(TestCase):
    def setUp(self):
        # Create a normal user and a superuser for admin access checks
        User = get_user_model()
        self.user = User.objects.create_user(username="tester", password="pass1234")
        self.admin = User.objects.create_superuser(username="admin", password="adminpass", email="admin@example.com")

        # Create minimal component objects for building a preview
        self.cpu = CPU.objects.create(name="CPU1", price=100)
        self.gpu = GPU.objects.create(gpu_name="GPU1", price=150)
        self.mobo = Motherboard.objects.create(name="Mobo1", price=80)
        self.ram = RAM.objects.create(name="RAM1", price=40)
        self.storage = Storage.objects.create(name="SSD1", price=60)
        self.psu = PSU.objects.create(name="PSU1", price=50)
        self.cooler = CPUCooler.objects.create(name="Cooler1", price=20)
        self.case = Case.objects.create(name="Case1", price=30)

        self.client = Client()

    def _set_preview_session(self):
        session = self.client.session
        session["preview_build"] = {
            "cpu": self.cpu.pk,
            "gpu": self.gpu.pk,
            "motherboard": self.mobo.pk,
            "ram": self.ram.pk,
            "storage": self.storage.pk,
            "psu": self.psu.pk,
            "cooler": self.cooler.pk,
            "case": self.case.pk,
            "budget": 500,
            "currency": "USD",
            "mode": "gaming",
            "score": 123,
            "price": 480,
        }
        session.save()

    def test_save_build_requires_login(self):
        """POSTing save_build without authentication should be redirected to login and no build created."""
        # Prepare session preview
        self._set_preview_session()

        resp = self.client.post(reverse("save_build"), follow=False)

        # Should be redirected to login (login_required) and not create a UserBuild
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)
        builds = UserBuild.objects.all()
        self.assertEqual(builds.count(), 0)

    def test_saved_builds_requires_login(self):
        """Accessing the saved builds index without authentication should redirect to login."""
        resp = self.client.get(reverse("saved_builds"))
        # login_required should redirect to the login page (302)
        self.assertEqual(resp.status_code, 302)
        # the redirect URL should include the login path
        self.assertIn("/accounts/login/", resp.url)

    def test_admin_panel_requires_superuser(self):
        """Ensure admin panel is protected: anonymous and normal users cannot access, superuser can."""
        # Anonymous access -> redirect to login
        resp = self.client.get("/admin/", follow=False)
        self.assertEqual(resp.status_code, 302)

        # Regular user login -> should not be allowed to access admin index (redirect to login)
        self.client.login(username="tester", password="pass1234")
        resp2 = self.client.get("/admin/", follow=False)
        # Non-superuser should be redirected (302) or denied
        self.assertNotEqual(resp2.status_code, 200)

        # Superuser can access (status 200)
        self.client.logout()
        self.client.login(username="admin", password="adminpass")
        resp3 = self.client.get("/admin/", follow=False)
        self.assertEqual(resp3.status_code, 200)

    def test_save_build_authenticated_creates_userbuild(self):
        """Posting save_build while authenticated should create a UserBuild owned by the logged-in user."""
        # Prepare session preview
        self._set_preview_session()

        # Login as normal user
        logged = self.client.login(username="tester", password="pass1234")
        self.assertTrue(logged)

        resp = self.client.post(reverse("save_build"), follow=True)

        # After successful save the view redirects to saved_builds
        self.assertEqual(resp.status_code, 200)

        builds = UserBuild.objects.filter(user__username="tester")
        self.assertEqual(builds.count(), 1)
        b = builds.first()
        self.assertIsNotNone(b)
        # basic sanity on stored fields
        self.assertEqual(float(b.total_price or 0), 480.0)
