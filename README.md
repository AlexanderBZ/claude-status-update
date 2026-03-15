# Claude Status Update

Generate a standup-ready status update from your Claude Code sessions. Run one command, automatically get a clean summary of what you built.

[![License|86](https://img.shields.io/github/license/jarrodwatts/claude-stt)](LICENSE) [![Stars](https://img.shields.io/github/stars/AlexanderBZ/claude-status-update)](https://github.com/AlexanderBZ/claude-status-update)

![cover](cover.png)

## Install

Inside a Claude Code instance, run the following commands:

**Step 1: Add the marketplace**

```
/plugin marketplace add [marketplace-url]
```

**Step 2: Install the plugin**

```
/plugin install status-update
```

Done! Run `/status-update` in any project to generate your status update.

---

## What is Claude Status Update?

Status Update analyzes your Claude Code session history and generates a clear standup-ready summary of what you worked on in the last 24 hours.

You get a short executive summary followed by categorized bullet points of your work.

| What You Get           | Why It Matters                                                |
| ---------------------- | ------------------------------------------------------------- |
| **Exec summary**       | 1–3 sentence overview of what you accomplished                |
| **Categorized output** | Work sorted into Bugs, Features, and Other                    |
| **24-hour scope**      | Only shows work from the current project, last 24 hours       |
| **Zero manual input**  | Reads directly from your Claude Code session traces           |
| **Local processing**   | All parsing done on-device; Claude classifies, not heuristics |

### How It Works

```
/status-update
       ↓
Python CLI parses ~/.claude/projects/[current-project]/*.jsonl
       ↓
Extracts user messages + AskUserQuestion responses from last 24h
       ↓
Groups extracted signals by session, writes to scratch file
       ↓
Claude reads signals, collapses each session into a work item,
classifies as bug / feature / other, writes exec summary
       ↓
Standup-ready text output to stdout
```

**Key details:**

- Deterministic parsing is done in Python CLI, no LLM involved in extraction
- Claude handles summarization and classification only
- Scratch file written to `$PWD/.status-update/signals.txt`, deleted after use
- Works best with sessions where you used plan mode or wrote messages describing intent, questions, and decisions

---

## Output Format

```
[Exec summary — 1–3 sentences describing what you worked on]

## Bugs
- [bug item]

## Features
- [feature item]

## Other
- [other item]
```

---

## Requirements

- **Python 3.10+**
- Claude Code with skill support

---

## Commands

| Command          | Description                                                        |
| ---------------- | ------------------------------------------------------------------ |
| `/status-update` | Generate a standup summary for the current project (last 24 hours) |

---

## Privacy

**All parsing is local:**

- Session traces are read from your local `~/.claude/projects/` directory
- Python CLI runs entirely on-device
- Scratch file is deleted after Claude reads it
- No session data is sent anywhere beyond your local Claude instance

---

## Contributing

Want to improve Claude Status Update?

1. Fork this repository
2. Make your changes
3. Submit a pull request

Please ensure your contribution:

- Addresses a real use case
- Doesn't break existing functionality
- Has been tested

---

## License

MIT — see [LICENSE](LICENSE)
