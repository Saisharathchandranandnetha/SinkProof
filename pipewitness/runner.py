"""Collector lifecycle: validate, start, send, stop, collect."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from pipewitness.fixtures import FixtureSet, build_otlp_payload

load_dotenv()


def _get_collector_image() -> str:
    return os.getenv("PW_COLLECTOR_IMAGE", "otel/opentelemetry-collector-contrib:latest")


def _free_port() -> int:
    """Find a free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _run_dir(run_id: str) -> Path:
    d = Path("runs") / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


class RunResult:
    """Result of a Collector run."""
    def __init__(self, run_id: str, run_dir: Path, image: str):
        self.run_id = run_id
        self.run_dir = run_dir
        self.image = image
        self.image_digest: str = ""
        self.captures_dir = run_dir / "captures"
        self.config_sha256: str = ""
        self.fixture_sha256: str = ""
        self.collector_logs: str = ""
        self.success: bool = False
        self.error: str | None = None


def is_docker_available() -> bool:
    """Check if docker binary is present and daemon is responding."""
    if not shutil.which("docker"):
        return False
    try:
        res = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=3,
        )
        return res.returncode == 0
    except Exception:
        return False


def validate_config(config_path: Path, image: str | None = None) -> tuple[bool, str]:
    """Validate a Collector config. Returns (valid, output)."""
    if not is_docker_available():
        try:
            from ruamel.yaml import YAML
            YAML().load(config_path.read_text())
            return True, "Valid YAML (static validation in sandbox mode)"
        except Exception as e:
            return False, f"YAML parse error: {e}"

    img = image or _get_collector_image()
    abs_cfg = str(config_path.resolve())
    try:
        result = subprocess.run(
            ["docker", "run", "--rm",
             "-v", f"{abs_cfg}:/etc/otelcol-contrib/config.yaml:ro",
             img,
             "validate", "--config=/etc/otelcol-contrib/config.yaml"],
            capture_output=True, text=True, timeout=30,
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output
    except Exception as e:
        return False, str(e)


def get_image_digest(image: str) -> str:
    """Get the pinned digest of the image."""
    if not is_docker_available():
        return image
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", image, "--format", "{{index .RepoDigests 0}}"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() or image
    except Exception:
        return image


def run_collector(
    config_path: Path,
    fixtures: FixtureSet,
    *,
    image: str | None = None,
    timeout_s: int = 30,
) -> RunResult:
    """Full Collector lifecycle: write config, start, send, stop, collect.
    
    Returns a RunResult with captures_dir pointing to the output.
    """
    img = image or _get_collector_image()
    run_id = uuid.uuid4().hex[:12]
    run_dir = _run_dir(run_id)
    result = RunResult(run_id=run_id, run_dir=run_dir, image=img)

    # Write config to run dir
    cfg_dest = run_dir / "config.yaml"
    cfg_text = config_path.read_text()
    cfg_dest.write_text(cfg_text)
    result.config_sha256 = hashlib.sha256(cfg_text.encode()).hexdigest()

    # Create captures dir with wide permissions (container runs as non-root)
    captures_dir = run_dir / "captures"
    captures_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(captures_dir, 0o777)
    except Exception:
        pass
    result.captures_dir = captures_dir

    # Fixture hash
    payload = build_otlp_payload(fixtures)
    payload_str = json.dumps(payload)
    result.fixture_sha256 = hashlib.sha256(payload_str.encode()).hexdigest()

    # Check Docker daemon availability
    if not is_docker_available():
        result.error = "Docker daemon is not available on this host (cloud sandbox mode)."
        return result

    # Get image digest
    result.image_digest = get_image_digest(img)

    # Find free port
    port = _free_port()
    container_name = f"pw-{run_id}"

    try:
        # Start container
        abs_cfg = str(cfg_dest.resolve())
        abs_captures = str(captures_dir.resolve())

        start_cmd = [
            "docker", "run", "-d",
            "--name", container_name,
            "-p", f"{port}:4318",
            "-v", f"{abs_cfg}:/etc/otelcol-contrib/config.yaml:ro",
            "-v", f"{abs_captures}:/captures",
            img,
        ]
        start_result = subprocess.run(start_cmd, capture_output=True, text=True, timeout=15)
        if start_result.returncode != 0:
            result.error = f"Failed to start: {start_result.stderr}"
            return result

        # Wait for readiness — retry POST until 200
        url = f"http://127.0.0.1:{port}/v1/logs"
        ready = False
        for attempt in range(30):
            try:
                resp = httpx.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=2.0,
                )
                if resp.status_code == 200:
                    ready = True
                    break
            except (httpx.HTTPError, httpx.RequestError):
                pass
            time.sleep(0.5)

        if not ready:
            result.error = "Collector not ready after 15s"
            return result

        # Wait for batch flush (batch timeout is 200ms in examples)
        time.sleep(2)

        # Graceful stop
        try:
            subprocess.run(
                ["docker", "stop", "-t", "10", container_name],
                capture_output=True, timeout=20,
            )
        except Exception:
            pass

        result.success = True

    except subprocess.TimeoutExpired:
        result.error = "Timeout during Collector run"
    except Exception as e:
        result.error = str(e)
    finally:
        try:
            logs_result = subprocess.run(
                ["docker", "logs", container_name],
                capture_output=True, text=True, timeout=10,
            )
            result.collector_logs = (logs_result.stdout + logs_result.stderr)
            (run_dir / "collector.log").write_text(result.collector_logs)
        except Exception:
            pass

        # Cleanup container safely
        try:
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass

    return result

