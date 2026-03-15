# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dev dependencies
uv sync

# Run tests
uv run python -m unittest discover -s tests

# Lint
uv run ruff check src/

# Test locally with Claude Code
claude --plugin-dir .
```

## Architecture

**Skill-based design**: A single `/status-update` command triggers a Python CLI that extracts signals from Claude Code session traces, then hands off to Claude for classification and summarization.

### Flow

```
/status-update
    → Python CLI parses ~/.claude/projects/[current-project]/*.jsonl
    → Extracts user messages + AskUserQuestion responses from last 24h
    → Groups signals by session → writes to $PWD/.status-update/signals.txt
    → Claude reads signals, classifies as bug/feature/other, writes exec summary
    → Standup-ready text output to stdout
    → Scratch file deleted
```

### Key Design Decisions

- **Deterministic extraction in Python** — no LLM involved in parsing session traces
- **Claude handles only summarization and classification** — keeps output reliable
- **Scratch file is ephemeral** — written to `$PWD/.status-update/signals.txt`, deleted after use
- **Scope is 24 hours, current project only**

### Plugin Structure

- `.claude-plugin/plugin.json` — plugin metadata (name, version, author)
- `.claude-plugin/marketplace.json` — marketplace listing metadata
- `src/claude_status_update/` — Python package source
  - `cli.py` — entry point (`claude_status_update.cli:main`)
- `tests/` — unittest test suite
- `pyproject.toml` — package config (hatchling build, uv dev deps: pytest, ruff)

## Output Format

```
[Exec summary — 1–3 sentences]

## Bugs
- [bug item]

## Features
- [feature item]

## Other
- [other item]
```

## Requirements

- Python 3.10–3.13
- uv (package manager)
- Claude Code with skill/plugin support

## Version Bumps

Update version in two files:
- `.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
