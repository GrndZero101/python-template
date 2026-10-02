---
name: git-workflow
description: >-
  How work moves through git in this project — branching before the first edit, Conventional
  Commit messages, checkpointing broken work, and finishing a branch into main with
  tools/finish_branch.py (squash or keep commits, always a --no-ff merge). Use when starting work,
  writing a commit message, committing half-done work, finishing or merging a branch, or when main
  has moved and conflicts with the branch.
---

# Git workflow

`main` is always a state you can return to. It only ever receives **merge commits**, one per
piece of work, so `git log --first-parent main` reads as a list of finished changes while plain
`git log` keeps the detail for `bisect`.

## 1. Start: branch before the first edit

```bash
git status --short --branch
git switch -c <type>/<short-name>      # feat/fetch-retry, fix/hook-stderr, chore/bump-ruff
```

- **Dirty tree?** Resolve it first — commit it, stash it, or ask. New work on top of someone else's
  uncommitted changes cannot be split into clean commits later.
- The branch type is the commit type you expect (see section 2).

Two guards back this up, and they catch different mistakes:

| Guard | Fires when | Effect |
|---|---|---|
| `PreToolUse` branch guard | `Edit`/`Write` to a file inside the repo while on `main` | blocks the edit before it lands |
| `no-commit-to-branch` | `git commit` on `main` | blocks the commit (merges are allowed) |

For a genuine one-line emergency, `touch .allow-main-edit` (gitignored) disables the edit guard
only. The commit guard then needs `git commit --no-verify`, which skips every other check too.
Branching costs one command; prefer it.

## 2. Commit: Conventional Commits

`type(scope): summary` — checked on every commit by `conventional-pre-commit`.

- **Types:** `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `build`, `ci`, `perf`, `style`,
  `revert`.
- **Summary:** imperative, lower case, no trailing period, at most 72 characters.
- **Scope** is optional: a module or area, e.g. `feat(cli): add --output csv`.
- **Breaking change:** `!` before the colon *and* a `BREAKING CHANGE:` footer.
- **Body** says *why*, not what — the diff already says what.
- **One logical change per commit.** If the summary needs "and", it is two commits.

### Checkpointing broken work

Scratch commits on a branch are fine and still use the format — `chore(x): wip`. Half-written
code will not pass `ty`, so skip the *code* checks but keep the *message* check:

```bash
SKIP=ruff-check,ruff-format,ty,rumdl-fmt,rumdl,conventions git commit -m "chore(x): wip"
```

Never `--no-verify` for this: it skips the message check too. Corrections to an earlier commit on
the branch can be `git commit --fixup=<sha>`; the finish step folds them in.

## 3. Finish: one command

```bash
uv run python tools/finish_branch.py "feat(geo): add coordinate lookup"
```

From the branch being finished, with a clean tree. It:

1. squashes the branch onto a fresh branch cut from the current `main`;
2. commits that with your message, so **the full gate and the message check run on it**;
3. merges it into `main` with `--no-ff` and the same subject;
4. deletes both branches.

A branch that is already one commit on top of `main` is merged as it is, and the message may be
left out to reuse that commit's subject.

| Situation | Command |
|---|---|
| The branch is one change (the usual case) | `finish_branch.py "type(scope): summary"` |
| It genuinely holds several changes, one commit each | `finish_branch.py --keep-commits "type(scope): summary of all"` |
| Stop before `main`, for someone to review | add `--no-merge` |

`--keep-commits` folds `fixup!` commits in with an autosquash rebase, runs
`prek run --all-files` (no hook runs during a rebase, so this is the only check the rebased tree
gets), and merges with `--log`, so the merge body lists the commits that arrived. Use it only when
squashing would produce an "and" commit.

**When it fails, nothing is lost.** Your branch is never rewritten on the default path. The
script returns you to it and says what to fix: the gate's findings, a rejected message, or a
conflict with `main`.

### The merge message

The merge commit is the only place the work is described: git records the branch name nowhere,
so once the branch is deleted its subject is all that is left.

- **Squash** (the default): the subject *is* the branch's one commit summary. That is why the
  script uses one message for both.
- **`--keep-commits`:** the subject summarises the branch as a whole; `--log` puts the individual
  commits in the body.
- Never git's default `Merge branch 'feat/x'`. The message check exempts anything starting with
  `Merge`, so nothing would catch it — the script always passes `-m`.
- Once there is a remote with PRs, add a `Refs: #N` trailer.

## When `main` has moved and conflicts

Resolve on the branch, never on `main`:

```bash
git rebase main          # on the branch; resolve each conflict, `git add`, `git rebase --continue`
prek run --all-files     # the rebase ran no hooks, so check the result
uv run python tools/finish_branch.py "type(scope): summary"
```

This is not just tidiness. Committing a *resolved* merge on `main` runs `pre-commit` rather than
`pre-merge-commit`, so `no-commit-to-branch` blocks it halfway and leaves the merge half-applied.

## By hand, if the script cannot run

The default path, step by step, for a branch `feat/x`:

```bash
git switch main
git switch -c feat/x-squashed
git merge --squash feat/x
git commit -m "feat(x): ..."                      # the full gate and message check run here
git switch main
git merge --no-ff -m "feat(x): ..." feat/x-squashed
git branch -D feat/x feat/x-squashed
```
