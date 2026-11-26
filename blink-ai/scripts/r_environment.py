"""Prepare the project-local R library and check the bundled GAPIT functions."""
import json
import os
from pathlib import Path
import subprocess
import sys

import blinkc_runner as runner


def setup(project_root, rscript=None, install=True, log_dir=None):
    project = Path(project_root).resolve()
    executable = str(Path(rscript).expanduser().resolve()) if rscript else runner.find_rscript()
    if not executable:
        raise ValueError("Rscript is unavailable. Install R from https://cran.r-project.org/ and set BLINK_AI_RSCRIPT to its executable.")
    metadata = runner.SKILL_ROOT / "assets/gapit/SOURCE.json"
    source = json.loads(metadata.read_text(encoding="utf-8"))
    for name, expected in source["files"].items():
        if runner.sha256_file(metadata.parent / name) != expected:
            raise ValueError("Bundled GAPIT function hash differs: " + name)
    library_base = Path(os.environ.get("BLINK_AI_R_LIBRARY", project / ".blink-ai/r-library")).expanduser().resolve()
    mirror = os.environ.get("BLINK_AI_CRAN_MIRROR", "https://cloud.r-project.org")
    install = install and os.environ.get("BLINK_AI_INSTALL_R_PACKAGES", "true").lower() != "false"
    logs = Path(log_dir) if log_dir else project / ".blink-ai/environment"
    logs.mkdir(parents=True, exist_ok=True)
    command = [executable, "--vanilla", str(runner.SKILL_ROOT / "scripts/setup_r_environment.R"),
               str(runner.SKILL_ROOT), str(library_base), str(install).lower(), mirror]
    record = {"status": "configuring", "rscript": executable, "library_base": str(library_base),
              "argv": command, "install_missing_packages": install, "repository": mirror}
    runner.write_json(logs / "r-environment.json", record)
    with (logs / "r-setup.stdout.log").open("wb") as stdout, (logs / "r-setup.stderr.log").open("wb") as stderr:
        try:
            result = subprocess.run(command, stdout=stdout, stderr=stderr, check=False, timeout=600)
            if result.returncode:
                detail = (logs / "r-setup.stderr.log").read_text(encoding="utf-8", errors="replace")[-2000:]
                raise ValueError("R environment setup failed: " + detail)
            # R package installation can print progress before the final JSON record.
            lines = (logs / "r-setup.stdout.log").read_text(encoding="utf-8").splitlines()
            record.update(json.loads(next(line for line in reversed(lines) if line.startswith("{"))))
        except (OSError, ValueError, StopIteration, subprocess.SubprocessError) as error:
            record.update(status="failed", error=str(error))
            runner.write_json(logs / "r-environment.json", record)
            raise ValueError("Cannot prepare the GAPIT R environment. See " + str(logs)) from error
    record.update(status="ready", gapit=source, checked_at=runner.utc_now())
    runner.write_json(logs / "r-environment.json", record)
    return record


def process_environment(info):
    env = dict(os.environ)
    env.update(BLINK_AI_RSCRIPT=info["rscript"], BLINK_AI_R_LIBRARY=info["library_base"],
               R_LIBS=os.pathsep.join(info["library_paths"]), BLINK_AI_PYTHON=sys.executable)
    return env
