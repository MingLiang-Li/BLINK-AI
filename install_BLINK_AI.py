#!/usr/bin/env python3
"""Install the bundled BLINK-AI skill into a Codex, TRAE, or Claude Code project."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
import uuid


SOURCE = Path(__file__).resolve().parent / "blink-ai"
HOSTS = {"codex": ".agents", "trae": ".trae", "claude": ".claude"}


def read_payload():
    receipt_bytes = (SOURCE / "PACKAGE.json").read_bytes()
    receipt = json.loads(receipt_bytes)
    payload = {"PACKAGE.json": receipt_bytes}
    for name, expected in receipt["files"].items():
        path = PurePosixPath(name)
        if path.is_absolute() or path.parts[0] != "blink-ai" or ".." in path.parts or "\\" in name:
            raise ValueError("Invalid file path in the package manifest")
        relative = Path(*path.parts[1:])
        file = SOURCE / relative
        if not file.resolve().is_relative_to(SOURCE.resolve()):
            raise ValueError("Package file escapes the skill directory")
        data = file.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("Package integrity check failed for " + str(relative))
        payload[relative.as_posix()] = data
    manifest = json.loads(payload["bin/manifest.json"])
    executables = {entry["path"] for group in ("engines", "conversion_tools") for entry in manifest[group]}
    return payload, executables


def install(host, project, payload, executables):
    project = project.expanduser().resolve()
    target = project / HOSTS[host] / "skills/blink-ai"
    if target.is_symlink() or not target.parent.resolve().is_relative_to(project):
        raise ValueError("The skill destination must stay inside the selected project")
    if project.is_relative_to(SOURCE.resolve()):
        raise ValueError("Choose a project outside the bundled skill directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.parent / (".blink-ai-staging-" + uuid.uuid4().hex)
    backup = None
    try:
        staged.mkdir()
        for name, data in payload.items():
            file = staged / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(data)
            file.chmod(0o755 if name in executables else 0o644)
        if target.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = project / ".blink-ai-backups" / host / (stamp + "-" + uuid.uuid4().hex[:6])
            backup.parent.mkdir(parents=True, exist_ok=True)
            target.rename(backup)
        try:
            staged.rename(target)
        except OSError:
            if backup and not target.exists():
                backup.rename(target)
            raise
    finally:
        if staged.exists():
            shutil.rmtree(staged)
    print(f"Installed BLINK-AI for {host} in {target}")
    if backup:
        print(f"Previous installation saved in {backup}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=["all", *HOSTS], default="all")
    parser.add_argument("--project", type=Path, default=Path.cwd(), help="Target project directory")
    args = parser.parse_args()
    payload, executables = read_payload()
    hosts = list(HOSTS) if args.host == "all" else [args.host]
    for host in hosts:
        install(host, args.project, payload, executables)
    print('Start a new session in the target project and ask, "Use BLINK-AI to check my environment and prepare an analysis for my data."')
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
