#!/usr/bin/env python3
"""Read-only tests for the actual Docker monitor-port isolation shell gate."""
from __future__ import annotations

import os
import re
import subprocess
import unittest
from pathlib import Path

RUNTIME = Path(__file__).with_name("runtime_validate.sh")


class MonitorHostPortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = RUNTIME.read_text(encoding="utf-8")
        match = re.search(r"(?ms)^assert_monitor_no_host_ports\(\) \{\n.*?^\}", cls.source)
        if not match:
            raise AssertionError("MONITOR_PORT_BINDING_GATE_MISSING")
        cls.shell_function = match.group()
        assert "HostConfig.PortBindings" in cls.shell_function
        assert "NetworkSettings.Ports" in cls.shell_function
        assert "docker compose \"\u0024{FILES[@]}\" port" not in cls.shell_function
        assert "docker inspect" in cls.shell_function

    def exercise(self, *, configured="", actual="", missing=False, inspect_fails=False):
        script = r"""
set -euo pipefail
FILES=(-f compose.yaml -f compose.staging.yaml)
fail() { printf 'REJECT:%s\n' "$*" >&2; exit 11; }
docker() {
  case "$1" in
    compose)
      [[ "${*: -1}" == cadvisor || "${*: -1}" == prometheus ]] || return 23
      if [[ "$MOCK_MISSING" == "1" ]]; then return 0; fi
      printf '0123456789abcdef\n'
      ;;
    inspect)
      if [[ "$MOCK_INSPECT_FAILS" == "1" ]]; then return 4; fi
      case "$*" in
        *HostConfig.PortBindings*) printf '%s' "$MOCK_CONFIGURED" ;;
        *NetworkSettings.Ports*) printf '%s' "$MOCK_ACTUAL" ;;
        *) return 9 ;;
      esac
      ;;
    *) return 8 ;;
  esac
}
""" + self.shell_function + """
assert_monitor_no_host_ports cadvisor
assert_monitor_no_host_ports prometheus
printf 'MONITOR_PORT_GATE=PASS\\n'
"""
        env = os.environ.copy()
        env.update({
            "MOCK_CONFIGURED": configured,
            "MOCK_ACTUAL": actual,
            "MOCK_MISSING": "1" if missing else "0",
            "MOCK_INSPECT_FAILS": "1" if inspect_fails else "0",
        })
        return subprocess.run(
            ["bash", "-c", script], env=env, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, timeout=8, check=False,
        )

    def test_no_exposed_monitor_host_ports_passes(self):
        p = self.exercise()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("MONITOR_PORT_GATE=PASS", p.stdout)

    def test_docker_exposed_but_not_published_passes(self):
        # Docker's effective JSON port mapping can be {"8080/tcp": null}.
        # Go template range over that null mapping yields zero host bindings.
        p = self.exercise(configured="", actual="")
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_configured_cadvisor_port_blocks(self):
        p = self.exercise(configured="0.0.0.0:8080 ")
        self.assertEqual(p.returncode, 11)
        self.assertIn("REJECT", p.stderr)

    def test_effectively_published_prometheus_port_blocks(self):
        p = self.exercise(actual="127.0.0.1:9090 ")
        self.assertEqual(p.returncode, 11)
        self.assertIn("REJECT", p.stderr)

    def test_empty_container_id_blocks(self):
        p = self.exercise(missing=True)
        self.assertEqual(p.returncode, 11)

    def test_docker_inspect_failure_blocks(self):
        p = self.exercise(inspect_fails=True)
        self.assertEqual(p.returncode, 11)

    def test_no_compose_port_heuristic(self):
        self.assertNotIn('docker compose "${FILES[@]}" port "$service"', self.shell_function)
        self.assertIn("HostConfig.PortBindings", self.shell_function)
        self.assertIn("NetworkSettings.Ports", self.shell_function)

    def test_shell_function_has_no_mutating_docker_verbs(self):
        self.assertNotRegex(
            self.shell_function,
            r"\bdocker\s+(?:rm|build|run|start|stop|restart|volume|network|kill|compose\s+.*?\s+up)\b",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
