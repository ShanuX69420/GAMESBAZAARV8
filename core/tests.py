from django.test import TestCase
from django.urls import reverse


class CoreViewsTests(TestCase):
    def test_home_page_loads(self):
        response = self.client.get(reverse("core:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "GamesBazaar")

    def test_health_check_returns_ok(self):
        response = self.client.get(reverse("core:health"))

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"status": "ok"})
