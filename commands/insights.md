---
description: Analyze Claude Code usage patterns and suggest improvements
allowed-tools: [Bash, Read]
---

# Learning Insights

Analyze recent Claude Code sessions and produce actionable recommendations for more effective usage.

## Step 1: Verify Python 3

Run `python3 --version`. If the command fails, try `python --version` instead. If neither succeeds, or the version is below 3.10, print:

> Python 3.10+ is required but not installed. Install it from https://python.org and try again.

Then stop. Use whichever command succeeded (`python3` or `python`) for all subsequent steps.

## Step 2: Run the analyzer

Execute (using whichever Python command was found in Step 1):

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/insights_analyzer.py"
```

The script writes `.status-update/insights.json` and prints the file path to stdout.

## Step 3: Read and parse insights

Use the Read tool to read `.status-update/insights.json`. Parse its contents as JSON. If the `insights` array is empty, inform the user:

> No usage patterns detected in the last 7 days that warrant recommendations. Keep using Claude Code and check back later.

Then delete `.status-update/insights.json` and stop.

## Step 4: Format recommendations

For each insight in the `insights` array, format a friendly recommendation block. Order by severity: `warning` first, then `info`.

Map each insight `type` to a human-readable title:

- `excessive_exploration` → "Reduce Exploration Overhead"
- `user_corrections` → "Prevent Misunderstandings"
- `repeated_prompts` → "Automate Repeated Tasks"
- `tool_errors` → "Reduce Tool Failures"
- `bash_misuse` → "Use Dedicated Tools"

Follow the writing style rules in `docs/guides/WRITING_STYLE.md`: no contractions, active voice, no em dashes, no weak openers, present habitual tense.

Format the final output as:

```
[1-2 sentence summary: e.g., "Analyzed 12 sessions over the last 7 days. Found 3 areas where you could use Claude Code more effectively."]

## Recommendations

### [Human-readable title from the type mapping above]
[Severity badge: "Action recommended" for warning, "Suggestion" for info]

[Recommendation text from the insight, expanded with the specific data. Use actual numbers and examples from the insight fields.]

[If the examples field exists, list 2-3 under "**Observed examples:**"]
```

## Step 5: Clean up

Delete `.status-update/insights.json` after formatting.
