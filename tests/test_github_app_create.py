"""Tests for lib/github_app_create.py (standard library only).

Run with: python3 -m unittest discover -s tests
"""

import importlib.util
import json
import os
import pathlib
import stat
import tempfile
import unittest

MODULE_PATH = pathlib.Path(__file__).parent.parent / "lib" / "github_app_create.py"
spec = importlib.util.spec_from_file_location("github_app_create", MODULE_PATH)
gac = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gac)


class BuildManifestTest(unittest.TestCase):
    def test_manifest_fields(self):
        manifest = gac.build_manifest(
            "my-app", "https://hook.example.com/abc", "http://127.0.0.1:1234/callback"
        )
        self.assertEqual(manifest["name"], "my-app")
        self.assertEqual(
            manifest["hook_attributes"],
            {"url": "https://hook.example.com/abc", "active": True},
        )
        self.assertEqual(manifest["redirect_url"], "http://127.0.0.1:1234/callback")
        self.assertFalse(manifest["public"])
        self.assertEqual(manifest["default_permissions"]["checks"], "write")
        self.assertEqual(manifest["default_permissions"]["metadata"], "read")
        self.assertIn("pull_request", manifest["default_events"])
        self.assertIn("push", manifest["default_events"])

    def test_manifest_is_json_serializable(self):
        manifest = gac.build_manifest("a", "https://h", "http://r")
        self.assertIn("hook_attributes", json.loads(json.dumps(manifest)))


class NewAppURLTest(unittest.TestCase):
    def test_personal(self):
        url = gac.github_new_app_url("https://github.com", "", "st4te")
        self.assertEqual(url, "https://github.com/settings/apps/new?state=st4te")

    def test_organization(self):
        url = gac.github_new_app_url("https://github.com/", "my-org", "s")
        self.assertEqual(
            url, "https://github.com/organizations/my-org/settings/apps/new?state=s"
        )

    def test_organization_is_quoted(self):
        url = gac.github_new_app_url("https://github.com", "a/b", "s")
        self.assertIn("/organizations/a%2Fb/", url)


class ParseConversionTest(unittest.TestCase):
    RESPONSE = {
        "id": 42,
        "slug": "my-app",
        "html_url": "https://github.com/apps/my-app",
        "pem": "-----BEGIN RSA PRIVATE KEY-----\nx\n-----END RSA PRIVATE KEY-----\n",
        "webhook_secret": "wh-secret",
        "client_secret": "ignored",
    }

    def test_valid_response(self):
        result = gac.parse_conversion(self.RESPONSE)
        self.assertEqual(result["id"], 42)
        self.assertEqual(result["slug"], "my-app")
        self.assertNotIn("client_secret", result)

    def test_missing_pem_raises(self):
        bad = dict(self.RESPONSE, pem="")
        with self.assertRaisesRegex(ValueError, "pem"):
            gac.parse_conversion(bad)

    def test_missing_id_raises(self):
        bad = {k: v for k, v in self.RESPONSE.items() if k != "id"}
        with self.assertRaisesRegex(ValueError, "id"):
            gac.parse_conversion(bad)


class WriteSecretsTest(unittest.TestCase):
    def test_writes_files_with_user_only_permissions(self):
        result = {
            "id": 42,
            "pem": "PEMDATA\n",
            "webhook_secret": "s3cret",
            "html_url": "https://github.com/apps/x",
            "slug": "x",
        }
        with tempfile.TemporaryDirectory() as tmp:
            outdir = os.path.join(tmp, "secrets")
            gac.write_secrets(outdir, result)
            appid = os.path.join(outdir, "github-application-id")
            with open(appid) as fp:
                self.assertEqual(fp.read(), "42\n")
            with open(os.path.join(outdir, "github-private-key")) as fp:
                self.assertEqual(fp.read(), "PEMDATA\n")
            with open(os.path.join(outdir, "webhook.secret")) as fp:
                self.assertEqual(fp.read(), "s3cret\n")
            mode = stat.S_IMODE(os.stat(appid).st_mode)
            self.assertEqual(mode, 0o600)


class LandingPageTest(unittest.TestCase):
    def test_form_posts_manifest(self):
        manifest = gac.build_manifest("a", "https://h", "http://r")
        page = gac.landing_page(
            "https://github.com/settings/apps/new?state=x", manifest
        ).decode()
        self.assertIn('action="https://github.com/settings/apps/new?state=x"', page)
        self.assertIn('name="manifest"', page)
        # the manifest JSON must be html-escaped inside the value attribute
        self.assertIn("&quot;hook_attributes&quot;", page)


class ManifestServerTest(unittest.TestCase):
    def setUp(self):
        import threading
        from http.server import HTTPServer

        self.server = HTTPServer(("127.0.0.1", 0), gac.ManifestHandler)
        self.port = self.server.server_address[1]
        self.server.landing_page = b"<html>landing</html>"
        self.server.expected_state = "st4te"
        self.server.expected_host = f"127.0.0.1:{self.port}"
        self.server.lock = threading.Lock()
        self.server.api_url = "https://api.invalid"
        self.server.result = None
        self.server.failure = ""
        self.server.done = threading.Event()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def _get(self, path, host=None):
        import http.client

        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("GET", path, headers={"Host": host or self.server.expected_host})
            resp = conn.getresponse()
            return resp.status, resp.read()
        finally:
            conn.close()

    def test_landing_page_served_only_once(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"landing", body)
        status, _ = self._get("/")
        self.assertEqual(status, 410)

    def test_rejects_unexpected_host_header(self):
        status, _ = self._get("/", host="attacker.example.com")
        self.assertEqual(status, 400)
        # landing page must still be available for the legitimate origin
        status, _ = self._get("/")
        self.assertEqual(status, 200)

    def test_callback_rejects_bad_state(self):
        status, _ = self._get("/callback?state=wrong&code=abc")
        self.assertEqual(status, 400)
        self.assertTrue(self.server.done.is_set())


if __name__ == "__main__":
    unittest.main()
