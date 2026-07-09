# 🎯 Golden Task Set — Evaluation Harness

> **Purpose:** A curated set of 10–20 coding tasks that serve as the **day-one benchmark** for the AI Dev-Team system. Every new component must improve performance on these tasks — or be cut.

## Why Golden Tasks?

From the [README](../README.md):

> *"Wire up SWE-bench Lite as the smoke test and pick 10–20 personal golden tasks **before writing any agent**. Never add a component without re-running this harness to prove it helped."*

## Task Format

Each task is defined in `tasks.yaml` with the following schema:

```yaml
- id: "golden-001"
  title: "Short descriptive title"
  description: |
    Detailed description of the coding task.
    Include the expected behavior, input, and output.
  language: "python"           # python | javascript | typescript | etc.
  difficulty: "easy"           # easy | medium | hard
  tags: ["bugfix", "refactor"] # categorization tags
  repo_url: ""                 # optional: link to a test repo
  input:
    files: {}                  # input files or context
    instructions: ""           # natural language task description
  expected:
    tests_pass: true           # must all tests pass?
    type_check: true           # must type-check cleanly?
    lint_clean: true           # must lint cleanly?
    custom_assertion: ""       # optional custom validation
```

## How to Add Tasks

1. Open `tasks.yaml` in this directory
2. Add a new task entry following the schema above
3. Run `make eval` to validate the harness
4. Aim for a diverse mix of difficulties and task types

## Recommended Task Categories

| Category | Examples | Count |
|---|---|---|
| Bug fixes | Off-by-one, null checks, exception handling | 3–5 |
| Refactoring | Extract function, rename, simplify logic | 2–3 |
| Feature addition | Add a CLI flag, new endpoint, config option | 3–5 |
| Test writing | Write tests for untested module | 2–3 |
| Data processing | Parse CSV, transform JSON, SQL query | 2–3 |

## Scoring

Each task is scored as:
- **✅ PASS** — Code runs, all tests pass, type-checks, lints clean
- **❌ FAIL** — Any verification step fails
- **⏱️ TIMEOUT** — Exceeded iteration cap

**North-Star Metric:** `% Resolved = (PASS / Total) × 100`
