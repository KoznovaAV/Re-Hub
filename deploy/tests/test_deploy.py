"""Проверки управления версиями без SSH и без настоящего Docker daemon."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOCKER = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
tag = os.environ.get("IMAGE_TAG", "")
with open("calls.jsonl", "a") as out:
    out.write(json.dumps([tag, args]) + "\\n")
command = args[3] if args[:2] == ["compose", "-f"] else ""
scenario = os.environ.get("SCENARIO", "")
if command == "ps" and "-q" in args:
    if scenario == "backup": print("db-container")
if command == "pull" and scenario == "pull": sys.exit(1)
if command == "up" and (scenario == "rollback_failed" or (scenario == "startup" and tag == "sha-new")): sys.exit(1)
if command == "exec":
    if "db" in args and scenario == "backup": sys.exit(1)
    if "backend" in args and scenario == "backend" and tag == "sha-new": sys.exit(1)
    if "parser-service" in args and scenario == "python" and tag == "sha-new": sys.exit(1)
'''


class DeploymentTest(unittest.TestCase):
    def run_script(self, scenario="", script="remote-deploy.sh", tag="sha-new"):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            docker = work / "docker"
            docker.write_text(DOCKER)
            docker.chmod(0o755)
            state = work / ".previous_image_tag"
            state.write_text("sha-old\n")
            env = {**os.environ, "PATH": f"{work}:{os.environ['PATH']}",
                   "IMAGE_TAG": tag, "IMAGE_OWNER": "test", "SCENARIO": scenario,
                   "BACKUP_BEFORE_DEPLOY": "1", "GHCR_TOKEN": "",
                   "PREVIOUS_FILE": str(state)}
            result = subprocess.run(["bash", str(ROOT / script)], cwd=work,
                                    env=env, capture_output=True, text=True)
            calls = (work / "calls.jsonl").read_text() if (work / "calls.jsonl").exists() else ""
            return result, state.read_text().strip(), calls

    def test_success_records_new_tag(self):
        result, tag, _ = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(tag, "sha-new")

    def test_pull_failure_keeps_previous_tag(self):
        result, tag, calls = self.run_script("pull")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(tag, "sha-old")
        self.assertNotIn('"up"', calls)

    def test_backup_failure_does_not_change_containers_or_tag(self):
        result, tag, calls = self.run_script("backup")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(tag, "sha-old")
        self.assertNotIn('"pull"', calls)

    def test_startup_and_each_health_failure_restore_previous_version(self):
        for scenario in ["startup", "backend", "python"]:
            with self.subTest(scenario=scenario):
                result, tag, calls = self.run_script(scenario)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(tag, "sha-old")
                self.assertIn("Previous version restored", result.stderr)
                self.assertIn('["sha-old", ["compose"', calls)

    def test_failed_rollback_is_reported(self):
        result, tag, _ = self.run_script("rollback_failed")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(tag, "sha-old")
        self.assertIn("automatic rollback failed", result.stderr)
        self.assertNotIn("Previous version restored", result.stderr)

    def test_manual_rollback_checks_backend(self):
        result, tag, _ = self.run_script("backend", "remote-rollback.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(tag, "sha-old")

    def test_manual_rollback_records_verified_tag(self):
        result, tag, _ = self.run_script(script="remote-rollback.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(tag, "sha-new")

    def test_invalid_tag_never_calls_docker(self):
        result, tag, calls = self.run_script(tag="bad tag")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(tag, "sha-old")
        self.assertEqual(calls, "")
