# Git Skill

## When to use it

Use this skill for git status, diffs, branch awareness, commit planning, merge conflict inspection, or safe handling of uncommitted changes.

## Useful commands

```bash
git status --short
git branch --show-current
git diff --stat
git diff
git log --oneline -5
```

## Project conventions

- Inspect status before summarizing changed files.
- Treat uncommitted changes as user-owned unless you made them during the current task.
- Prefer read-only git commands unless the user explicitly asks for a mutating action.
- Ask before `git add`, `git commit`, `git push`, `git reset`, `git checkout`, or `git clean`.

## Common traps

- Do not revert unrelated changes.
- Do not commit without explicit approval.
- Do not overwrite uncommitted work to make a patch easier.
- Remember that some workspaces may not be git repositories.

## Done criteria

- Current branch and dirty files are understood when git context matters.
- Diffs are reviewed before reporting file changes.
- Mutating git operations are approved by the user.
- The final status separates changed files, validation, and unresolved items when appropriate.
