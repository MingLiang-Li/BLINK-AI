# Install BLINK-AI

Copy the complete `blink-ai` directory into the skills directory in your project.

| Host | Project path |
|---|---|
| Codex | `.agents/skills/blink-ai` |
| Claude Code | `.claude/skills/blink-ai` |
| TRAE | `.trae/skills/blink-ai` |

Start a new session in that project and ask, “Use BLINK-AI to run the bundled GWAS example.”

The dual-platform package includes native executables for Apple silicon macOS and x86-64 Windows. Install Python 3.9 or later and R. The setup command prepares a project-local R library, installs `jsonlite` when missing, and loads the bundled GAPIT plotting and simulation functions.

```bash
python3 "SKILL_DIR/scripts/blinkc_runner.py" setup-environment --project-root .
```

Set `BLINK_AI_RSCRIPT` or `runtime.rscript` to the Rscript executable if automatic discovery fails. See [commands](SKILL.md#commands) for the environment check and example.
