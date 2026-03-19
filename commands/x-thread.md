---
description: Generate a viral X thread to market a new plugin feature
allowed-tools: [Bash, Read]
---

# X Thread Generator

Generate a copy-paste-ready X (Twitter) thread to promote a new feature of the Claude Status Update plugin.

## Step 1: Determine the feature

If `$ARGUMENTS` is non-empty, use it as the feature description. Proceed to Step 2.

If `$ARGUMENTS` is empty, gather context to suggest a feature description:

1. Read `${CLAUDE_PLUGIN_ROOT}/CHANGELOG.md` for recent entries.
2. Run `git -C "${CLAUDE_PLUGIN_ROOT}" log --oneline -10` to see recent commits.

From these sources, draft a one-sentence feature description and present it to the user:

> Based on recent changes, it looks like the feature is: **[your suggestion]**
>
> Does this look right? Reply with a correction or confirm to proceed.

Wait for the user to confirm or revise. Do not proceed until the user approves the feature description.

If neither source yields useful content, ask the user to provide a feature description and stop.

## Step 2: Gather product context

Read these files to ground the thread in accurate product details:

- `${CLAUDE_PLUGIN_ROOT}/README.md` — plugin positioning, install instructions, value propositions
- `${CLAUDE_PLUGIN_ROOT}/docs/guides/WRITING_STYLE.md` — prose style reference

## Step 3: Generate the thread

Write an X thread following ALL of these rules. Every rule matters.

### Thread structure

- **5 to 10 posts total.** This is the sweet spot for developer engagement.
- **Post 1 (the hook):** Under 280 characters. Tease a problem the reader has, or promise a concrete benefit. This post must reference a hero image: include `[Attach: cover.png]` on its own line after the post text. The hook decides whether anyone reads the rest. Make it count.
- **Posts 2 through N-1 (the body):** Under 280 characters each. One idea per post. Build a narrative arc: problem, then solution, then proof. Each post should make readers want to read the next one.
- **Post N (the closer):** Include a clear call to action. Link the GitHub repo: `https://github.com/AlexanderBZ/claude-status-update`. End with a question that invites replies. Limit hashtags to 1-2 relevant ones, only in this final post.

### Content strategy

These rules reflect what works on X for technical audiences in 2026:

- **Hook with authority or a specific problem.** "I got tired of writing standups manually" beats "Excited to announce our new feature!" Generic openers get scrolled past.
- **Show, do not tell.** Use concrete examples: "Run /status-update:generate. 30 seconds later, your standup is done." Specifics build credibility.
- **Demonstrate technical depth.** Mention implementation details that signal competence: deterministic Python parsing, no LLM in the extraction pipeline, local-only processing, ephemeral scratch files. Developers respect builders who explain how things work.
- **Include social proof where available.** Star count, MIT license, two-command install. Low friction signals drive adoption.
- **Write as a builder, not a marketer.** The tone is a developer sharing what they built with peers. No corporate voice. No hype words ("revolutionary", "game-changing", "excited to announce"). First person is fine.
- **No hashtag spam.** One or two relevant tags at most, only in the final post. Developers distrust hashtag-heavy threads.
- **Maximize early engagement potential.** The first 30 minutes after posting determine algorithmic reach. The thread should be designed to earn quick likes, replies, and reposts. Questions, surprising claims, and relatable pain points drive early interaction.

### Writing style

Adapted for social media from the project writing style guide:

- Active voice, present tense.
- No em dashes. Use colons or separate sentences.
- No weak openers ("It is," "There is," "There are").
- Contractions are allowed. Character efficiency matters at 280 chars. Sound natural.
- Casual-technical tone. You are a builder talking to other builders.
- Vary rhythm. Mix short punchy posts with slightly longer ones.

### Character counting

Every post MUST be 280 characters or fewer. Count carefully. URLs count as 23 characters on X regardless of actual length. Emoji count as 2 characters. When in doubt, leave a buffer of 5-10 characters.

## Step 4: Validate

Before outputting, construct a JSON object representing the thread and validate it:

```
echo '$THREAD_JSON' | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate_thread.py"
```

The JSON format:

```json
{
  "posts": [
    {"number": 1, "content": "post text here", "has_image": true},
    {"number": 2, "content": "post text here", "has_image": false}
  ],
  "total_posts": 7
}
```

If validation fails, revise the thread to fix the issue and re-validate. Do not output a thread that fails validation.

## Step 5: Output the thread

Print the final thread in this format:

```
# X Thread: [feature name]

**Best posting window:** Tuesday-Thursday, 8-11 AM ET
**Thread length:** N posts
**Hero image:** Attach cover.png to the first post

---

[1/N] (142 chars)
Post content here

[Attach: cover.png]

---

[2/N] (198 chars)
Post content here

---

...

[N/N] (237 chars)
Final post with CTA and repo link
```

Each post shows its number and character count. The user copies each post into X sequentially, replying to the previous post to form the thread.
