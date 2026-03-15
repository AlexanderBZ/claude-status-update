# Status Update Plugin — Shaping

---

## Requirements (R)

| ID  | Requirement                                                                                                                         | Status    |
| --- | ----------------------------------------------------------------------------------------------------------------------------------- | --------- |
| R0  | `/status-update` command produces a standup-ready text output                                                                       | Core goal |
| R1  | Output includes an exec summary (1-3 sentences)                                                                                     | Core goal |
| R2  | Output categorizes work into bugs fixed, features built, refactor, and other                                                        | Core goal |
| R3  | Deterministically extract all user input from JSONL traces (user messages + AskUserQuestion tool responses)                         | Core goal |
| R4  | Scope covers the last 24 hours for the current project only                                                                         | Must-have |
| R5  | Output is text to stdout — no file written                                                                                          | Must-have |
| R6  | Classification (bug / feature / refactor / other) is done by Claude, not heuristics                                                 | Must-have |
| R7  | Plugin is a skill that delegates deterministic parsing to a CLI script                                                              | Must-have |
| R8  | CLI written in Python                                                                                                               | Must-have |
| R9  | CLI groups messages by session (deterministic); Claude collapses each session group into a single work item                         | Must-have |
| R10 | CLI writes extracted signals to a scratch file in PWD; Claude reads it then the skill deletes it on cleanup                         | Must-have |
| R11 | All deterministic work (parsing, filtering, grouping) lives in the CLI; Claude is invoked only for summarization and classification | Must-have |

---

## Shape A: Skill + Python CLI Parser + Claude Classifier

### Architecture

```
/status-update
    │
    ▼
Skill prompt (~/.claude/skills/status-update.md)
    │  instructs Claude to run the CLI via Bash tool
    ▼
~/.claude/scripts/status_update_parser.py
    │  encodes $PWD → project slug (replace / and spaces with -)
    │  walks ~/.claude/projects/[slug]/*.jsonl only
    │  reads last line per file; includes if timestamp >= now - 24h
    │  for included files: iterates all lines
    │    extracts type:user / isMeta:false / message.content (string)
    │    extracts tool_result content where tool_use_id matches
    │      an AskUserQuestion tool_use in the same file
    │  groups extracted messages by session file (one block per JSONL)
    │  labels each block with timestamp of first real user entry
    │  writes structured signals to $PWD/.[plugin-name]/signals.txt
    │  prints file path to stdout
    ▼
Skill instructs Claude to read $PWD/.[plugin-name]/signals.txt via Read tool
    ▼
Claude reads signals from scratch file (on demand, not inline)
    │  collapses each session group into a work item description
    │  classifies each work item: bug / feature / refactor / other
    │  writes 1-3 sentence exec summary
    │  formats three categorized bullet lists
    ▼
Skill instructs Claude to delete $PWD/.[plugin-name]/signals.txt via Bash tool
    ▼
Text output to stdout
```

### Parts

| Part   | Mechanism                                                                                                                                                                                                         | Flag |
| ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--: |
| **A1** | **Python JSONL parser CLI**                                                                                                                                                                                       |      |
| A1.1   | Derive project slug: `$PWD` with all `/` and spaces replaced by `-` (leading `-` kept); confirmed against live `~/.claude/projects/` listing                                                                      |      |
| A1.2   | Read last line per JSONL file; parse `timestamp` field; include file if `timestamp >= now - 24h`; fall back to file mtime if needed                                                                               |      |
| A1.3   | For included files, iterate all lines; extract `message.content` (string) from entries where `type == "user"` and `isMeta != true`                                                                                |      |
| A1.4   | Extract `tool_result` content where `tool_use_id` matches a `tool_use` block named `AskUserQuestion` in any assistant entry in the same file                                                                      |      |
| A1.5   | Group extracted messages by session file; label each block with `timestamp` of first real user entry (filename is a UUID, not a timestamp); write to `$PWD/.[plugin-name]/signals.txt`; print file path to stdout |      |
| **A2** | **Skill prompt**                                                                                                                                                                                                  |      |
| A2.1   | Instructs Claude to run `python3 ~/.claude/scripts/status_update_parser.py` via Bash tool; if `python3` not found, print error asking user to install Python 3 and stop                                           |      |
| A2.2   | Instructs Claude to read `$PWD/.[plugin-name]/signals.txt` via Read tool; then delete it via Bash tool after reading                                                                                              |      |
| **A3** | **Claude classifier + summarizer**                                                                                                                                                                                |      |
| A3.1   | Reads signals from `$PWD/.[plugin-name]/signals.txt` (not inline context); file deleted via Bash after reading                                                                                                    |      |
| A3.2   | Collapse each session group's messages into a single work item description                                                                                                                                        |      |
| A3.3   | Classify each work item as `bug`, `feature`, or `other`                                                                                                                                                           |      |
| A3.4   | Write 1-3 sentence exec summary                                                                                                                                                                                   |      |
| A3.5   | Output: exec summary block, then `## Bugs`, `## Features`, `## Other` bullet lists                                                                                                                                |      |

---

## Fit Check: R × A

| Req | Requirement                                                                                                                            | Status    | A   |
| --- | -------------------------------------------------------------------------------------------------------------------------------------- | --------- | --- |
| R0  | `/status-update` command produces a standup-ready text output                                                                          | Core goal | ✅   |
| R1  | Output includes an exec summary (1-3 sentences)                                                                                        | Core goal | ✅   |
| R2  | Output categorizes work into bugs fixed, features built, and other                                                                     | Core goal | ✅   |
| R3  | Deterministically extract all user input from JSONL traces (user messages + AskUserQuestion tool responses)                            | Core goal | ✅   |
| R4  | Scope covers the last 24 hours for the current project only                                                                            | Must-have | ✅   |
| R5  | Output is text to stdout — no file written                                                                                             | Must-have | ✅   |
| R6  | Classification (bug / feature / other) is done by Claude, not heuristics                                                               | Must-have | ✅   |
| R7  | Plugin is a skill that delegates deterministic parsing to a CLI script                                                                 | Must-have | ✅   |
| R8  | CLI written in Python                                                                                                                  | Must-have | ✅   |
| R9  | CLI groups messages by session (deterministic); Claude collapses each session group into a single work item                            | Must-have | ✅   |
| R10 | CLI writes extracted signals to `$PWD/.[plugin-name]/signals.txt`; Claude reads it via Read tool; skill deletes it via Bash on cleanup | Must-have | ✅   |
| R11 | All deterministic work (parsing, filtering, grouping) lives in the CLI; Claude invoked only for summarization and classification       | Must-have | ✅   |

**Notes:** No failures. Shape A satisfies all requirements.
