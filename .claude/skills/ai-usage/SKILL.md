# ai-usage — Session AI Usage Tracker

Scoped to: `PR-Review-Agent` project.

## Trigger

Invoked via `/ai-usage` or `/ai-usage update`.  
Also run automatically at the end of any task session when the user asks for a summary.

## What this skill does

Read the current conversation context and update `ai_usage.md` in the project root with accurate, up-to-date tracking data. Never fabricate counts — derive them from actual tool calls and file operations visible in the conversation.

## Instructions

### Step 1 — Load current state

Read `ai_usage.md` if it exists. Parse the existing counts so you can increment rather than overwrite.

### Step 2 — Analyse this session

From the conversation context, extract:

**Tools used**
Count every tool call by name: `Read`, `Write`, `Edit`, `Bash`, `PowerShell`, `Grep`, `Glob`, `Agent`, `Artifact`, `Skill`, `Workflow`, etc. Increment existing counts.

**Skills**
List every skill invoked in this session (via `/skill-name` or `Skill` tool). Record the skill name and how many times it fired this session. Add to cumulative per-skill totals.

**Slash commands & subagents**
List every `/command` used and every `Agent`/`Workflow` subagent spawned, with a brief note on purpose.

**Files — AI-generated vs human-written**
- AI-generated: any file created or substantially rewritten by Claude (`Write` tool, or `Edit` that replaced >50% of content).
- Human-written: files the user wrote or that existed before Claude touched them in this session.
- Accepted: file writes/edits the user approved (not rejected via the permission prompt).
- Rejected: tool calls the user denied.

**Bugs introduced / fixed**
- Introduced: any bug in AI-generated code that required a follow-up fix.
- Fixed: bugs found in existing code and corrected by Claude.

### Step 3 — Write ai_usage.md

Use the template below. Preserve all existing rows and append/update only what changed this session. Add a new session block under `## Session Log` each time the skill fires.

---

## Template

```markdown
# AI Usage Log — PR-Review-Agent

> Auto-maintained by the `/ai-usage` skill. Updated each session.

## Summary

| Metric | Count |
|---|---|
| Total sessions tracked | N |
| Total tool calls (AI) | N |
| Files AI-generated | N |
| Files human-written | N |
| Files accepted | N |
| Files rejected | N |
| Bugs introduced by AI | N |
| Bugs fixed by AI | N |
| **AI-written %** | **N%** |
| **Human-written %** | **N%** |

## Tool Call Totals

| Tool | Times Called |
|---|---|
| Read | N |
| Write | N |
| Edit | N |
| Bash | N |
| PowerShell | N |
| Grep | N |
| Glob | N |
| Agent / Workflow | N |
| Skill | N |
| Artifact | N |
| Other | N |

## Skills Authored & Fired

| Skill Name | Authored By | Times Fired |
|---|---|---|
| ai-usage | human-directed / AI-written | N |

## Slash Commands & Subagents Used

| Command / Subagent | Purpose | Times |
|---|---|---|
| /ai-usage | Update AI usage log | N |

## Session Log

### Session N — YYYY-MM-DD

**Task:** (one-line description of what was done)

**Tools called this session:**
- Read: N, Write: N, Edit: N, Bash: N, PowerShell: N, Grep: N, Glob: N

**Files touched:**
| File | Action | Origin |
|---|---|---|
| path/to/file | created / edited / deleted | AI / human |

**Accepted / Rejected:**
- Accepted: N file operations
- Rejected: N (list any with reason if known)

**Bugs:**
- Introduced: N
- Fixed: N

**Notes:** (anything notable — tricky decisions, rejects, approach changes)
```

### Step 4 — Report back

After writing, print a one-paragraph summary of what changed this session: tools called, files touched, any rejected operations, and the current AI vs human percentage.
