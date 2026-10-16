"""Run the native Terraform CLI/provider against an isolated loopback API fixture."""

import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class NativeTerraformTests(unittest.TestCase):
    def test_profile_lifecycle_import_replacement_drift_and_failures(self):
        terraform = os.environ.get("TERRAFORM_BIN") or shutil.which("terraform")
        self.assertTrue(terraform, "Install the pinned Terraform CLI")
        with tempfile.TemporaryDirectory(prefix="notte-terraform-") as directory:
            root = Path(directory)
            plugins = root / "plugins"
            plugins.mkdir()
            subprocess.run(["go", "build", "-o", str(plugins / "terraform-provider-notte"), "."], check=True)
            profiles = {}
            counter = 0
            closed = set()
            flags = {"forbidden": False, "delete_rejected": False}
            lock = threading.Lock()

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *_args):
                    pass

                def respond(self, status, data):
                    self.send_response(status)
                    if status == 400:
                        self.send_header("X-Error-Class", "ProfileAlreadyClosedError")
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(data).encode())

                def do_POST(self):
                    nonlocal counter
                    if self.path != "/profiles/create" or self.headers.get("Authorization") != "Bearer test-only":
                        return self.respond(403, {"detail": "private-fixture-detail"})
                    body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                    with lock:
                        counter += 1
                        identifier = f"notte-profile-{counter:016x}"
                        profiles[identifier] = {
                            "profile_id": identifier,
                            "name": body.get("name"),
                            "cookies": "private-cookie-fixture",
                        }
                        self.respond(200, profiles[identifier])

                def do_GET(self):
                    if flags["forbidden"]:
                        return self.respond(403, {"detail": "private-fixture-detail"})
                    identifier = self.path.removeprefix("/profiles/")
                    with lock:
                        self.respond(200, profiles[identifier]) if identifier in profiles else self.respond(
                            400 if identifier in closed else 404, {}
                        )

                def do_DELETE(self):
                    identifier = self.path.removeprefix("/profiles/")
                    with lock:
                        if flags["delete_rejected"]:
                            return self.respond(200, {"success": False})
                        profiles.pop(identifier, None)
                        closed.add(identifier)
                        self.respond(200, {"success": True})

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            config = root / "terraform.rc"
            config.write_text(
                "provider_installation {\n dev_overrides { "
                f'"nottelabs/notte" = "{plugins.as_posix()}"'
                " }\n direct {}\n}\n"
            )
            env = {
                **{key: value for key, value in os.environ.items() if not key.startswith("TF_")},
                "TF_CLI_CONFIG_FILE": str(config),
                "TF_IN_AUTOMATION": "1",
                "CHECKPOINT_DISABLE": "1",
                "NOTTE_API_KEY": "test-only",
                "NOTTE_API_URL": f"http://127.0.0.1:{server.server_port}",
            }
            env.pop("TF_LOG", None)
            env.pop("TF_LOG_PATH", None)
            env.pop("TF_CLI_ARGS", None)

            def cli(*arguments, expected=0):
                result = subprocess.run(
                    [terraform, *arguments, "-no-color"], cwd=root, env=env, text=True, capture_output=True, timeout=120
                )
                self.assertNotIn("private-fixture-detail", result.stdout + result.stderr)
                self.assertNotIn("private-cookie-fixture", result.stdout + result.stderr)
                if result.returncode != expected:
                    self.fail(
                        f"Terraform {' '.join(arguments)} returned {result.returncode}:\n"
                        f"{result.stdout}\n{result.stderr}"
                    )
                return result.stdout

            def configuration(name):
                attribute = "" if name is None else f"name = {json.dumps(name)}"
                (root / "main.tf").write_text(
                    'terraform {\n required_providers {\n notte = { source = "nottelabs/notte" }\n }\n}\n'
                    'provider "notte" {}\nresource "notte_profile" "example" {\n' + attribute + "\n}\n"
                )

            def resource_id():
                data = json.loads(cli("show", "-json"))
                values = data["values"]["root_module"]["resources"][0]["values"]
                self.assertEqual(set(values), {"id", "name"})
                return values["id"]

            try:
                configuration("first")
                schemas = json.loads(cli("providers", "schema", "-json"))
                provider = schemas["provider_schemas"]["registry.terraform.io/nottelabs/notte"]
                self.assertTrue(provider["provider"]["block"]["attributes"]["api_key"]["sensitive"])
                cli("apply", "-auto-approve", "-input=false")
                identifier = resource_id()
                self.assertEqual(profiles[identifier]["name"], "first")
                cli("plan", "-detailed-exitcode", "-input=false")
                with lock:
                    profiles[identifier]["name"] = "external-change"
                cli("plan", "-detailed-exitcode", "-input=false", "-out=drift.plan", expected=2)
                drift = json.loads(cli("show", "-json", "drift.plan"))
                self.assertEqual(drift["resource_changes"][0]["change"]["actions"], ["delete", "create"])
                configuration("second")
                cli("apply", "-auto-approve", "-input=false")
                replacement = resource_id()
                self.assertNotEqual(identifier, replacement)
                self.assertNotIn(identifier, profiles)
                cli("state", "rm", "notte_profile.example")
                cli("import", "-input=false", "notte_profile.example", replacement)
                cli("plan", "-detailed-exitcode", "-input=false")
                with lock:
                    profiles.pop(replacement)
                    closed.add(replacement)
                cli("plan", "-detailed-exitcode", "-input=false", "-out=missing.plan", expected=2)
                missing = json.loads(cli("show", "-json", "missing.plan"))
                self.assertEqual(missing["resource_changes"][0]["change"]["actions"], ["create"])
                cli("apply", "-auto-approve", "-input=false")
                recreated = resource_id()
                flags["forbidden"] = True
                cli("plan", "-input=false", expected=1)
                self.assertEqual(resource_id(), recreated)
                flags["forbidden"] = False
                flags["delete_rejected"] = True
                cli("destroy", "-auto-approve", "-input=false", expected=1)
                self.assertEqual(resource_id(), recreated)
                flags["delete_rejected"] = False
                cli("destroy", "-auto-approve", "-input=false")
                self.assertFalse(profiles)
                configuration(None)
                cli("apply", "-auto-approve", "-input=false")
                cli("plan", "-detailed-exitcode", "-input=false")
                cli("destroy", "-auto-approve", "-input=false")
                self.assertFalse(profiles)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
