"""Exercise deployment choices without starting containers or contacting Cloudflare."""

import os
from pathlib import Path
import pty
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def run_deploy(tmp_path, answers=None, saved_token=False, args=()):
    shutil.copy(ROOT / "deploy.sh", tmp_path)
    (tmp_path / ".env").write_text("ADMIN_PASSWORD=existing-password\n")
    if saved_token:
        (tmp_path / ".cloudflared.env").write_text("TUNNEL_TOKEN=saved-token\n")
    docker = tmp_path / "docker"
    docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$DOCKER_LOG"\n')
    docker.chmod(0o755)
    env = dict(os.environ, PATH=f"{tmp_path}:{os.environ['PATH']}",
               DOCKER_LOG=str(tmp_path / "docker.log"))
    env.pop("CST_DOMAIN", None)
    master, slave = pty.openpty()
    try:
        process = subprocess.Popen(
            ["bash", str(tmp_path / "deploy.sh"), *args],
            stdin=slave if answers is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
        )
        if answers is not None:
            os.write(master, answers.encode())
        output, _ = process.communicate(timeout=10)
        assert process.returncode == 0, output.decode()
        return output.decode(), (tmp_path / "docker.log").read_text()
    finally:
        os.close(master)
        os.close(slave)


def test_local_noninteractive(tmp_path):
    output, calls = run_deploy(tmp_path)
    assert "localhost" in output
    assert "compose.tunnel.yml" not in calls
    assert not (tmp_path / ".cloudflared.env").exists()
    assert (tmp_path / ".env").read_text() == "ADMIN_PASSWORD=existing-password\n"


def test_guided_tunnel_setup(tmp_path):
    output, calls = run_deploy(tmp_path, answers="y\nexample-token_123=\n")
    assert "-f compose.tunnel.yml up" in calls
    assert "http://app:8000" in output
    assert "example-token_123=" not in output + calls
    token_file = tmp_path / ".cloudflared.env"
    assert token_file.read_text() == "TUNNEL_TOKEN=example-token_123=\n"
    assert token_file.stat().st_mode & 0o777 == 0o600


def test_reuse_saved_tunnel_noninteractive(tmp_path):
    output, calls = run_deploy(tmp_path, saved_token=True)
    assert "Reusing" in output
    assert "-f compose.tunnel.yml up" in calls
    assert "saved-token" not in output + calls


def test_declining_stops_existing_tunnel_before_local_start(tmp_path):
    _, calls = run_deploy(tmp_path, answers="n\n", saved_token=True)
    assert calls.index("stop cloudflared") < calls.index("up --build")
    assert "compose -f compose.yml up" in calls


def test_cancel_token_setup(tmp_path):
    output, calls = run_deploy(tmp_path, answers="y\n\n")
    assert "cancelled" in output
    assert "compose.tunnel.yml" not in calls
    assert not (tmp_path / ".cloudflared.env").exists()


def test_invalid_answers_and_full_commands_are_reprompted(tmp_path):
    output, calls = run_deploy(
        tmp_path, answers="maybe\ny\ndocker run --token wrong\nvalid-token\n"
    )
    assert "Please answer yes or no" in output
    assert "Paste only the token" in output
    assert "-f compose.tunnel.yml up" in calls
    assert (tmp_path / ".cloudflared.env").read_text() == "TUNNEL_TOKEN=valid-token\n"


def test_domain_mode_stops_old_tunnel(tmp_path):
    output, calls = run_deploy(
        tmp_path, saved_token=True, args=("--domain", "cst.example.com")
    )
    assert "https://cst.example.com" in output
    assert "-f compose.https.yml up" in calls
    assert calls.index("stop cloudflared") < calls.index("up --build")
