"""Local user feedback, run evidence, and issue verification records."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import platform
import re
import sys
import uuid

import blinkc_runner as runner

STATUSES = ("received", "analyzing", "fixing", "fixed", "verified", "closed")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evidence_file(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ValueError("Evidence file is missing: " + str(path))
    return {"path": str(path), "sha256": runner.sha256_file(path)}


def run_evidence(run_dir):
    root = Path(run_dir).expanduser().resolve()
    result = {"run_dir": str(root), "run_id": root.name, "files": [], "logs": []}
    # Summaries contain identities, QC, commands, and versions without loading genotype matrices.
    for name in ("manifest.json", "config.input.json", "config.resolved.json", "context.json",
                 "conversion.json", "failure.json", "results/summary.json", "results/R-session.json",
                 "results/plotting.json", "logs/r-environment.json"):
        path = root / name
        if not path.is_file():
            continue
        result["files"].append(evidence_file(path))
        if name in ("manifest.json", "conversion.json", "failure.json", "results/summary.json", "logs/r-environment.json"):
            result[name] = read_json(path)
    for folder in (root / "logs", root / "work"):
        if folder.is_dir():
            result["logs"].extend(str(path) for path in sorted(folder.rglob("*.log")) if path.is_file())
    return result


def check_validation(items):
    if not isinstance(items, list):
        raise ValueError("validation must be a list")
    checked = []
    for item in items:
        if not isinstance(item, dict) or not item.get("check") or item.get("result") not in ("pending", "passed", "failed"):
            raise ValueError("Each validation needs a check and a pending, passed, or failed result")
        files = [evidence_file(path) for path in item.get("evidence", [])]
        if item["result"] in ("passed", "failed") and not files:
            raise ValueError("Completed validation requires an existing evidence file")
        checked.append({"check": item["check"], "result": item["result"], "evidence": files})
    return checked


def validate_changes(changes):
    if not isinstance(changes, list):
        raise ValueError("changes must be a list")
    for change in changes:
        if not isinstance(change, dict) or not all(change.get(key) for key in ("function", "location", "reason", "before", "after")):
            raise ValueError("Code changes require function, location, reason, before, and after")
    return changes


def render(record):
    def quoted(value, fallback):
        return "\n".join("> " + line for line in (value if value else fallback).splitlines())

    lines = ["# BLINK-AI feedback report", "", "## Basic information", "",
             f"- Feedback ID `{record['id']}`", f"- Created {record['created_at']}",
             f"- Skill version {record['skill_version']}", f"- Reporter {record['reporter']}",
             "", "## User requirements", "", quoted(record["user_request"], "Original user wording was not supplied."),
             "", "Recorded operation", "", quoted(record.get("operation"), "Not supplied."),
             "", "## User experience", "", quoted(record["user_experience"], "The user has not evaluated the experience."),
             "", "## Issues and suggestions", "", quoted(record["issue"], "Not supplied."), "",
             f"- Category {record['category']}", f"- Expected behavior {record.get('expected') or 'Not supplied.'}",
             f"- Actual behavior {record.get('actual') or 'Not supplied.'}",
             f"- Impact {record.get('impact') or 'Not assessed.'}",
             "", "### Run evidence", "", "```json", json.dumps(record.get("run", {}), ensure_ascii=False, indent=2), "```",
             "", "## Functional code changes", ""]
    if record["changes"]:
        lines += ["```json", json.dumps(record["changes"], ensure_ascii=False, indent=2), "```"]
    else:
        lines.append("No code changes recorded.")
    lines += ["", "## Handling status", "", f"- Status {record['status']}", f"- Priority {record['priority']}",
              f"- First seen in version {record['first_seen_version']}",
              f"- Fixed in version {record.get('fixed_in_version') or 'Not established.'}",
              "", "### Validation", "", "```json", json.dumps(record["validation"], ensure_ascii=False, indent=2), "```",
              "", "### History", "", "```json", json.dumps(record["history"], ensure_ascii=False, indent=2), "```"]
    if record.get("regression"):
        lines += ["", "### Regression case", "", "```json", json.dumps(record["regression"], ensure_ascii=False, indent=2), "```"]
    return "\n".join(lines) + "\n"


def write_report(path, record):
    text = render(record)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def create(project_root, details, run_dir=None, automatic=False):
    project = Path(project_root).expanduser().resolve()
    if not isinstance(details, dict):
        raise ValueError("Feedback details must be a JSON object")
    if not automatic and (not isinstance(details.get("user_request"), str) or not details["user_request"].strip()):
        raise ValueError("User feedback requires the original user_request")
    if not isinstance(details.get("issue"), str) or not details["issue"].strip():
        raise ValueError("Feedback requires an issue description")
    for field in ("user_request", "user_experience", "reporter", "operation", "expected", "actual", "impact"):
        if details.get(field) is not None and not isinstance(details[field], str):
            raise ValueError(field + " must be a string or null")
    if details.get("priority", "medium") not in ("low", "medium", "high"):
        raise ValueError("Feedback priority must be low, medium, or high")
    now = datetime.now().astimezone()
    project_id = hashlib.sha256(str(project).encode("utf-8")).hexdigest()[:10]
    reports = project / "feedback_data/reports"
    reports.mkdir(parents=True, exist_ok=True)
    snapshot = run_evidence(run_dir) if run_dir else {}
    affected = snapshot.get("manifest.json", snapshot.get("conversion.json", {}))
    record = {"schema_version": "1", "created_at": now.isoformat(timespec="seconds"),
              "skill_version": runner.VERSION, "project_id": project_id, "kind": "failure" if automatic else "user",
              "reporter": details.get("reporter") or "Not supplied", "user_request": details.get("user_request"),
              "operation": details.get("operation"), "user_experience": details.get("user_experience"),
              "issue": details["issue"], "category": details.get("category", "other"),
              "expected": details.get("expected"), "actual": details.get("actual"), "impact": details.get("impact"),
              "priority": details.get("priority", "medium"), "status": "received",
              "first_seen_version": details.get("first_seen_version", affected.get("version", affected.get("tool_version", runner.VERSION))), "fixed_in_version": None,
              "changes": validate_changes(details.get("changes", [])), "validation": [],
              "run": snapshot,
              "environment": {"system": platform.system(), "architecture": platform.machine(), "python": sys.version},
              "history": [{"at": runner.utc_now(), "status": "received", "note": "Local feedback recorded"}]}
    while True:
        record["id"] = f"BLINK_AI_feedback_{now:%Y%m%d}_{project_id}_{uuid.uuid4().hex}"
        path = reports / (record["id"] + ".json")
        try:
            with path.open("x", encoding="utf-8") as handle:
                json.dump(record, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            break
        except FileExistsError:
            continue
    write_report(path.with_suffix(".md"), record)
    return {"id": record["id"], "report": str(path.with_suffix(".md")), "record": str(path)}


def update(project_root, identifier, details):
    if not isinstance(details, dict):
        raise ValueError("Feedback updates must be a JSON object")
    if not re.fullmatch(r"BLINK_AI_feedback_[A-Za-z0-9_]+", identifier):
        raise ValueError("Invalid feedback ID")
    path = Path(project_root).expanduser().resolve() / "feedback_data/reports" / (identifier + ".json")
    lock = path.with_suffix(".lock")
    lock.open("x", encoding="ascii").close()
    try:
        record = read_json(path)
        status = details.get("status", record["status"])
        if status not in STATUSES or not details.get("note"):
            raise ValueError("A supported status and handling note are required")
        checks = {item["check"]: item for item in record["validation"]}
        checks.update({item["check"]: item for item in check_validation(details.get("validation", []))})
        validation = list(checks.values())
        if status in ("verified", "closed") and (not validation or any(item["result"] != "passed" for item in validation)):
            raise ValueError("Verified or closed status requires passing evidence for every recorded check")
        record.update(status=status, validation=validation)
        record["changes"].extend(validate_changes(details.get("changes", [])))
        user_context = {}
        for field in ("user_request", "user_experience", "reporter", "expected", "actual", "impact"):
            if field in details:
                if not isinstance(details[field], str) or not details[field].strip():
                    raise ValueError(field + " must be a nonempty string")
                user_context[field] = {"before": record.get(field), "after": details[field]}
                record[field] = details[field]
        for field in ("fixed_in_version", "first_seen_version"):
            if field in details:
                record[field] = details[field]
        if "regression" in details:
            case = details["regression"]
            if not isinstance(case, dict) or not all(case.get(key) for key in ("reproduction_steps", "expected_behavior", "verification_criteria")):
                raise ValueError("Regression cases require reproduction steps, expected behavior, and verification criteria")
            if status not in ("fixed", "verified", "closed"):
                raise ValueError("Confirm and fix the issue before registering a regression case")
            record["regression"] = {**case, "case_id": identifier, "first_seen_version": record["first_seen_version"],
                                    "fixed_in_version": record["fixed_in_version"]}
        if record.get("regression"):
            record["regression"].update(first_seen_version=record["first_seen_version"], fixed_in_version=record["fixed_in_version"])
        record["history"].append({"at": runner.utc_now(), "status": status, "note": details["note"],
                                  "validation": details.get("validation", []), "user_context": user_context})
        runner.write_json(path, record)
        write_report(path.with_suffix(".md"), record)
        if record.get("regression"):
            cases = path.parent.parent / "regressions"
            cases.mkdir(exist_ok=True)
            runner.write_json(cases / (identifier + ".json"), record["regression"])
    finally:
        lock.unlink(missing_ok=True)
    return {"id": identifier, "status": status, "report": str(path.with_suffix(".md"))}


def record_failure(project_root, error, operation, run_dir=None, request=None, experience=None):
    result = create(project_root, {"user_request": request, "user_experience": experience,
                    "operation": operation, "issue": str(error), "actual": str(error), "category": "execution"},
                    run_dir=run_dir, automatic=True)
    if run_dir and (Path(run_dir) / "manifest.json").is_file():
        path = Path(run_dir) / "manifest.json"
        manifest = read_json(path)
        manifest["feedback"] = result
        runner.write_json(path, manifest)
        record_path = Path(result["record"])
        record = read_json(record_path)
        record["run"] = run_evidence(run_dir)
        runner.write_json(record_path, record)
        write_report(record_path.with_suffix(".md"), record)
    print("Local feedback report " + result["report"], file=sys.stderr)
    return result
