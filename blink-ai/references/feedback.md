# Local feedback and issue tracking

Record each user problem, error, suggestion, or code change request under the project root in `feedback_data/reports/`. Each record has a Markdown report and a JSON record with the same ID. IDs combine the local date, a project identifier, and a random identifier. Reports are created exclusively to avoid overwriting concurrent feedback.

The report retains six sections in order. They are Basic information, User requirements, User experience, Issues and suggestions, Functional code changes, and Handling status. Quote the user's wording. Leave the experience unevaluated when the user has supplied no assessment. An analysis completing successfully provides technical evidence about that run.

## Create a report

Save the user's feedback in a UTF-8 JSON file. For example, this input records a user's request and experience verbatim.

```json
{
  "user_request": "Create a Manhattan plot and a QQ plot for Height.",
  "user_experience": "I can find the Manhattan plot but not the QQ plot.",
  "issue": "The expected QQ plot could not be found.",
  "category": "plotting",
  "expected": "Both plot files are available in the report.",
  "actual": "The user found one plot.",
  "priority": "medium"
}
```

```bash
python3 "SKILL_DIR/scripts/blinkc_runner.py" feedback-create --project-root . --input feedback.json --run-dir runs/height
```

Omit `--run-dir` when the feedback has no associated analysis. The command prints the feedback ID and local report paths. The run snapshot includes versions, hashes, stage, commands, QC and result summaries when available, and references to logs. Preserve `context.json` with the analysis for the input identity and allele metadata.

The standard `run` and conversion CLI capture execution failures automatically, including failures before a result table exists. Missing original user wording and experience remain explicitly unprovided. Set `feedback.user_request` and `feedback.user_experience` in an analysis configuration when that context is available. Set `runtime.project_root` when the configuration resides outside the user's project. Otherwise, the configuration directory is the default project root. The demo uses the current project directory.

## Update handling status

Use the existing ID to retain the history of an issue. Supported statuses are `received`, `analyzing`, `fixing`, `fixed`, `verified`, and `closed`. Every update requires a handling note. Provide the original user request or experience in an update when adding that context to an automatic failure record.

```json
{
  "status": "analyzing",
  "note": "Reproducing the missing QQ plot with the recorded configuration.",
  "validation": [
    {"check": "QQ PDF exists and is linked in the report", "result": "pending"}
  ]
}
```

```bash
python3 "SKILL_DIR/scripts/blinkc_runner.py" feedback-update --project-root . --id FEEDBACK_ID --input update.json
```

Supply each code change with `function`, `location`, `reason`, `before`, and `after` fields in the `changes` array. Use the function name and a descriptive code location. Add compatibility findings with their evidence when established. Supply `first_seen_version` and `fixed_in_version` only as known.

Validation items use a `check`, a `result` of `pending`, `passed`, or `failed`, and an `evidence` array of existing local file paths for completed checks. Evidence hashes are recorded. An update for the same check replaces its current outcome while retaining the handling history. `verified` and `closed` require passing evidence for all recorded checks.

## Register a regression case

After confirming a fix, add a `regression` object to a handling update. Include `reproduction_steps`, `expected_behavior`, and `verification_criteria`. The case is stored in `feedback_data/regressions/` with its feedback ID, first observed version, and fixed version. Preserve the local reproduction inputs and validation evidence with the issue. Use these cases alongside the bundled evaluation scenarios when checking a release. Registering a case records the acceptance criteria. Test execution and its results must be recorded separately as validation evidence.

Feedback reports are local project artifacts. Submit them to a maintainer through a channel selected by the user when the user asks to share them.
