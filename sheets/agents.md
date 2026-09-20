# Agent harnesses · keep work reviewable

**F6** toggle this sheet · F1 tmux · F2 Vim · F3 search · F5 git

## Reach first

```sh
git status -sb       # know the checkout and any existing edits
codex               # start Codex here
claude              # start Claude Code here
gemini              # start Gemini CLI here
agy                 # start Antigravity CLI here
```

Run one harness per task in its own tmux session and Git worktree.
Read this repo's instructions before editing. Keep secrets out of prompts,
commits, logs and handoffs.

## Continue a conversation

```sh
codex resume         # choose a Codex session
claude -c            # continue Claude's most recent conversation here
gemini --resume latest
agy -c               # continue Antigravity's most recent conversation
```

Use each harness's `--help` for session selection and changed options.
Resume in the same project; check the branch and working tree again.

## A useful first request

> Read the repo instructions and current issue. Trace the affected path and
> its callers. Make the smallest fix, run the relevant check, then show the
> diff, test result and remaining risk.

Give the agent an issue or observable failure, acceptance criteria and
constraints. Ask for a checkpoint before a long run.

## Check the result

```sh
git diff --check           # whitespace errors
git diff                   # unstaged edits
git diff --staged          # exact proposed commit
git status -sb             # untracked or unrelated work
```

Read the changed code and run the repo's own check before merging. In a
shared checkout, stage exact paths; leave other work untouched.

## When a run gets messy

- Ask for current branch, changed paths, completed checks and next step.
- Make a short handoff with issue link, commit, test result and blocker.
- Start a fresh session for a new task; resume only the same task.
- Use `cheat git` for worktrees, diffs and recovery commands.
