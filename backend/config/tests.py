from unittest.mock import patch

from django.test import SimpleTestCase


class HealthEndpointTests(SimpleTestCase):
    @patch("config.views.connection")
    def test_healthy_database_returns_ok(self, mock_connection):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"status": "ok"})
        mock_connection.cursor.assert_called_once_with()

    @patch("config.views.connection")
    def test_missing_database_returns_503_without_details(self, mock_connection):
        mock_connection.cursor.side_effect = OSError("private connection details")
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 503)
        self.assertJSONEqual(response.content, {"status": "unavailable"})
        self.assertNotIn(b"private connection details", response.content)
