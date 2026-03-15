---
shape: status-update-plugin
---

# Status Update Plugin — Slices

Each slice is a vertical cut that can be built and tested independently. Work top-to-bottom or in parallel where noted.

> **Out of scope:** Users who primarily interact via `@`-mentions with short surrounding messages are not supported. Claude Code does not write `@file` content into JSONL, so there is nothing for the parser to extract from those sessions. This is by design — do not attempt to handle it in any slice.

---

## Slice 1 — CLI: File Discovery

**Delivers:** A runnable CLI that correctly identifies which JSONL session files belong to the current project and fall within the last 24 hours.

**Parts covered:** A1.1, A1.2

**Work:**
- Create `~/.claude/scripts/status_update_parser.py`
- Derive project slug from `$PWD` (replace `/` and spaces with `-`)
- Confirm slug against actual `~/.claude/projects/` directory listing
- Read last line of each JSONL file; parse `timestamp` field; include file if `>= now - 24h`; fall back to file mtime if needed
- Print matched file paths to stdout (no signals file yet)

**Done when:** Running the script from a project directory prints the correct session files and nothing from other projects or outside the 24h window.

---

## Slice 2 — CLI: Signal Extraction

**Delivers:** A `signals.txt` file with all user messages and `AskUserQuestion` responses grouped by session, ready for Claude to read.

**Parts covered:** A1.3, A1.4, A1.5

**Depends on:** Slice 1 (file list)

**Work:**
- For each included JSONL file, iterate all lines
- Extract `message.content` (string) where `type == "user"` and `isMeta != true`
- Collect all `tool_use` entries named `AskUserQuestion` across assistant lines; extract `tool_result` content where `tool_use_id` matches
- Group both into a session block labeled with the `timestamp` of the first real user entry
- Write all blocks to `$PWD/.status-update/signals.txt`; print file path to stdout

**Done when:** Inspecting `signals.txt` directly shows clean, grouped session blocks with all user-supplied text and no assistant content.

---

## Slice 3 — Skill Wiring (End-to-End, No AI Summarization)

**Delivers:** `/status-update` runs the CLI, reads `signals.txt`, deletes it, and prints the raw signals to stdout. Proves the full plumbing works before adding Claude's summarization step.

**Parts covered:** A2.1, A2.2

**Can start in parallel with:** Slice 2 (skill prompt can be drafted while CLI is being built)

**Work:**
- Create `~/.claude/skills/status-update.md`
- Instruct Claude to run `python3 ~/.claude/scripts/status_update_parser.py` via Bash; halt with install message if `python3` not found
- Instruct Claude to read the printed file path via Read tool
- Instruct Claude to delete `$PWD/.status-update/signals.txt` via Bash after reading
- For now, have Claude echo the raw signals as output (placeholder for Slice 4)

**Done when:** `/status-update` from a project directory prints the raw grouped signals and leaves no scratch file behind.

---

## Slice 4 — Claude Summarization

**Delivers:** The full standup-ready output: exec summary + categorized bullet lists.

**Parts covered:** A3.1–A3.5

**Depends on:** Slice 3 (skill wiring in place)

**Work:**
- Update skill prompt to instruct Claude to collapse each session block into a single work item description
- Classify each work item as `bug`, `feature`, or `other`
- Write a 1–3 sentence exec summary
- Format output as:
  ```
  [exec summary paragraph]

  ## Bugs
  - …

  ## Features
  - …

  ## Other
  - …
  ```
- Remove the raw-echo placeholder from Slice 3

**Done when:** `/status-update` produces a clean, standup-ready report with no raw signals visible and correct categorization.
