---
description: Generate a standup-ready status update from recent Claude Code sessions
allowed-tools: [Bash, Read, Agent]
---

# Status Update

Generate a categorized standup report from the last 24 hours of Claude Code sessions.

## Step 1: Verify Python 3

Run `python3 --version`. If the command fails, print:

> Python 3 is required but not installed. Install it from https://python.org and try again.

Then stop.

## Step 2: Run the parser

Execute:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/status_update_parser.py"
```

The script writes `.status-update/signals.json` and prints the file path to stdout. Do not delete this file after reading.

## Step 3: Read and parse signals

Use the Read tool to read `.status-update/signals.json`. Parse its contents as JSON. If the `sessions` array is empty, inform the user:

> No Claude Code activity found in the last 24 hours.

Then stop.

## Step 4: Summarize each session

For each session in the `sessions` array, spawn a Haiku subagent (`model: "haiku"`) in parallel using the Agent tool. Provide the following prompt to each subagent, filling in the session signals:

```
You are a work-item extractor. Analyze the following signals from a single Claude Code session and identify each distinct piece of work performed.

Return ONLY a JSON array of objects. Each object has exactly two fields:
- "description": a concise summary of the work in imperative mood (e.g., "Fix login timeout", "Add dark mode toggle")
- "category": exactly one of "bug", "feature", "refactor", "research", or "other"

A single session may contain multiple work items spanning different categories. Combine closely related signals into one work item rather than listing each signal separately.

Do not include any text outside the JSON array. Do not wrap in markdown code fences.

Session signals:
$SESSION_SIGNALS
```

Replace `$SESSION_SIGNALS` with the JSON-encoded signals array for that session.

## Step 5: Validate responses

For each subagent response, extract the JSON array from the response text. Pipe it through the validation script:

```
echo '$RESPONSE_JSON' | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate_summary.py"
```

The script exits 0 if valid. If it exits non-zero, report the validation error and skip that session.

## Step 6: Aggregate and format

Collect all validated work items across sessions. Group them by category. Write a 1-3 sentence executive summary that captures the overall thrust of the work. Follow the writing style rules in `docs/guides/WRITING_STYLE.md`: no contractions, active voice, no em dashes, no weak openers, present habitual tense.

Format the final output as:

```
[executive summary]

## Bugs
- [description]

## Features
- [description]

## Refactors
- [description]

## Other
- [description]
```

Omit any category section that has no items. Print the formatted report directly to the user.
