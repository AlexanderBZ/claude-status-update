---
description: Analyze Claude Code usage patterns and suggest improvements
allowed-tools: [Bash, Read]
---

# Learning Insights

Analyze recent Claude Code sessions and produce specific, evidence-based recommendations for more effective usage.

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

## Step 3: Read and parse evidence

Use the Read tool to read `.status-update/insights.json`. Parse its contents as JSON.

If no categories are triggered (check `summary.categories_triggered == 0`), inform the user:

> No usage patterns detected in the last 7 days that warrant recommendations. Keep using Claude Code and check back later.

Then delete `.status-update/insights.json` and stop.

## Step 4: Systematic Behavior Analysis

You are now a behavior analyst. You have structured evidence from the user's Claude Code sessions. Your job is to diagnose root causes and prescribe specific, implementable actions.

### 4.1 — Claude Code Effectiveness Dimensions

Organize your findings into these dimensions of effective Claude Code usage:

| Dimension | What it measures | Evidence source |
|-----------|-----------------|-----------------|
| **Context Provisioning** | How well the user equips Claude with project knowledge | `exploration_patterns` |
| **Communication Precision** | How clearly user and Claude understand each other | `correction_events` |
| **Workflow Efficiency** | Whether repetitive tasks are automated | `repeated_prompts` |
| **Tool Utilization** | Whether Claude uses the right tools for each job | `bash_misuse`, `tool_errors` |
| **Session Productivity** | How effectively each session produces outcomes | `session_profiles` + cross-category |

Only include dimensions that have triggered categories. Skip dimensions with no evidence.

### 4.2 — Per-Category Analysis Guide

For each triggered category, follow this structured analysis:

#### exploration_patterns (maps to Context Provisioning)

1. Read `statistics.exploration_ratio` and `statistics.exploration_count` — understand the scale
2. Examine `evidence.files_read_multiple_times` — these are files Claude keeps re-reading because it lacks context about them
3. Examine `evidence.exploration_bursts` — long sequences of searching triggered by a prompt. Look at the `preceding_prompt` to understand what caused each burst
4. Examine `evidence.frequent_search_terms` — these are concepts Claude has to repeatedly search for

**Diagnose root causes:**
- Files read multiple times → those files or their purpose should be documented in CLAUDE.md so Claude knows where to look
- Long exploration bursts after vague prompts → the user should provide specific file paths or more context in their prompts
- Frequent search terms → the related architecture or concepts should be documented in CLAUDE.md

**Prescribe specific actions:**
- Name the exact files that should be documented
- Write the actual CLAUDE.md lines the user should add (using the file paths and search terms from the evidence)
- If exploration bursts follow vague prompts, show how to rephrase those prompts with file paths

#### correction_events (maps to Communication Precision)

1. Read `statistics.correction_count` and `statistics.sessions_with_corrections`
2. Examine `evidence.events` — look at each correction alongside its `preceding_actions` and `original_prompt`

**Diagnose root causes:**
- Corrections after edits to wrong files → Claude misunderstood the scope. The user should specify which files to touch (and which NOT to touch)
- Corrections about approach → Claude lacks constraints. Document constraints in CLAUDE.md under a Gotchas section
- Repeated corrections about the same issue → a persistent misunderstanding that needs a CLAUDE.md entry

**Prescribe specific actions:**
- Write the actual Gotchas entries for CLAUDE.md based on the correction content
- Show how the original prompts could be improved with constraints

#### repeated_prompts (maps to Workflow Efficiency)

1. Read `statistics.group_count`
2. Examine `evidence.groups` — look at examples and `sessions_seen_in`

**Diagnose root causes:**
- Prompts repeated across many sessions (high `sessions_seen_in`) → habitual workflow that should be automated as a slash command
- Prompts repeated within one session (low `sessions_seen_in`) → retry behavior, likely caused by failures

**Prescribe specific actions:**
- For habitual prompts: suggest creating a slash command in `commands/` directory. Show the actual command file content
- For retry prompts: identify what is causing the retry and fix the root cause

#### tool_errors (maps to Tool Utilization)

1. Read `statistics.total_errors`, `statistics.error_rate`, `statistics.errors_by_tool`
2. Examine `evidence.error_examples` — actual error content reveals the root cause

**Diagnose root causes:**
- Bash errors with permission issues → tool permission configuration
- Read errors with wrong paths → Claude does not know the project structure. Document it in CLAUDE.md
- Repeated errors on the same tool → a systemic issue (missing dependency, wrong config)

**Prescribe specific actions:**
- Quote the actual error content and explain what it means
- Provide the specific fix (permission change, CLAUDE.md entry, dependency install)

#### bash_misuse (maps to Tool Utilization)

1. Read `statistics.misuse_count` and `statistics.total_bash_calls`
2. Examine `evidence.examples` — the commands and their suggested replacements

**Diagnose root causes:**
- Using `cat` instead of Read, `grep` instead of Grep → Claude may lack tool permissions, or the user may be instructing Claude to use bash commands

**Prescribe specific actions:**
- If the CLAUDE.md instructs bash usage, suggest removing those instructions
- If tool permissions may be restricted, suggest checking allowed-tools configuration

### 4.3 — Cross-Category Correlation

Look for patterns that span multiple triggered categories:

- **High exploration + frequent corrections** = Claude lacks context, acts on incomplete understanding → priority: document architecture in CLAUDE.md
- **Repeated prompts + tool errors** = a workflow keeps failing → priority: fix the underlying tool issue, then automate
- **Bash misuse + tool errors on Bash** = tool permission issues → priority: update allowed-tools configuration
- **High exploration ratio + low errors** = Claude is careful but slow → context documentation will speed things up without losing quality

Note cross-category correlations in your output when found.

### 4.4 — Prescription Quality Rules

Every recommendation you produce MUST include:
1. **What to do** — a specific, implementable action (never "consider improving" or "think about")
2. **Concrete example** — actual text, code, or config to write, derived from the evidence
3. **Where to do it** — file path or configuration location
4. **Why it helps** — which observed behavior it addresses, citing specific numbers from the evidence

Bad example: "Consider adding more context to your CLAUDE.md to reduce exploration."
Good example: "Claude reads `src/auth/handler.py` an average of 7 times per session because the authentication architecture is not documented. Add to your CLAUDE.md:\n```\n## Architecture\n- Authentication: `src/auth/handler.py` handles login/logout. Token validation in `src/auth/tokens.py`.\n```\nThis addresses the 82% exploration ratio by giving Claude direct file paths."

### 4.5 — Claude Code Best Practices Reference

Draw from these best practices when prescribing actions:
- **CLAUDE.md** is the primary context mechanism; it loads automatically at conversation start
- **Slash commands** (`commands/*.md`) automate repetitive multi-step workflows
- **Hooks** (`settings.json`) automate reactive workflows (post-commit, pre-push)
- **Specific prompts** with file paths and constraints produce better results than vague requests
- **Dedicated tools** (Read, Grep, Glob, Edit, Write) are faster and more reliable than Bash equivalents
- **Gotchas sections** in CLAUDE.md prevent recurring misunderstandings
- **Project structure docs** in CLAUDE.md reduce exploration overhead

## Step 5: Format output

Follow the writing style rules in `docs/guides/WRITING_STYLE.md`: no contractions, active voice, no em dashes, no weak openers, present habitual tense.

Format the final output as:

```
[1-2 sentence executive summary citing specific numbers from metadata, e.g. "Analyzed 12 sessions (487 tool calls) over the last 7 days. Found 3 patterns affecting exploration efficiency and communication precision."]

## [Dimension Name]

### [Finding title — specific to the evidence, not generic]
[Severity badge: "Action recommended" for warning, "Suggestion" for info]

[Analysis paragraph: what was observed (citing numbers), why it matters, root cause diagnosis — all referencing specific evidence]

**Action:** [Specific prescription with file path]

[Code block or config snippet the user can copy-paste, if applicable]

[Cross-category correlation note, if applicable]
```

Order dimensions by severity (warning dimensions first, then info). Within a dimension, order findings by severity.

## Step 6: Clean up

Delete `.status-update/insights.json` after formatting.
