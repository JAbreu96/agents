---
name: stacked-pr
description: Ship a multi-phase feature as a stack of small PRs, one per phase, each based on the previous. Use when an approved plan has more than one phase, when a change is heading past ~500 lines or ~10 files, or when a merged parent leaves its children needing a restack.
argument-hint: "(no arguments required)"
---

Ship a multi-phase feature as a **stack**: one PR per phase, each based on the previous, only
the bottom one on `main`.

The plan is the cut list. An approved plan already names the phases; each phase is one branch
and one PR. Nothing here asks you to invent seams — it asks you to keep the ones the plan
already found.

## When a stack is the shape

Stack when any of these holds:

- The approved plan has more than one phase.
- The change is heading past **~500 lines** or **~10 files**.
- The work crosses more than one layer — schema, endpoints, UI, templates.

A single-phase change under the budget ships as one ordinary PR against `main`.

## Cut the stack

**One phase, one PR.** If the plan says Phase 0 / 1a / 1b / 1c / 2, that is five PRs, in that
order.

**Put pure refactors at the bottom.** An extraction, a rename, a move with no behaviour change
goes first, as its own PR, before anything that builds on it. Two payoffs: the reviewer can
verify "nothing changed" in one pass, and every later phase writes the new code once instead of
once per view. A refactor that lands underneath is also the seam that stops two later phases
colliding in the same file.

**Keep each PR inside the budget.** ~500 lines, ~10 files. The budget is a tripwire, not a
gate: cross it deliberately and say why in the PR body, under **Worth a reviewer's attention**.
A verified pure move can be large and still trivially reviewable; a 200-line schema change with
a migration deserves its own rung. Judge by what a reviewer must hold in their head.

**Each rung stands on its own.** The full suite passes at every level, not only at the top. A
reviewer merging the bottom three and stopping must be left with working software.

## Build it

Branch each phase off the previous phase's head:

```bash
git checkout -b phase-1-data-layer      # while on the phase-0 branch
```

Push and open each PR against the branch below it:

```bash
git push -u origin phase-1-data-layer
gh pr create --base phase-0-extraction --head phase-1-data-layer \
  --title "..." --body-file <path>
```

Only the bottom PR takes `--base main`.

Confirm each PR landed on the right rung — a PR that silently targets `main` swallows every
phase beneath it and undoes the stack:

```bash
gh pr view <n> --json baseRefName,files -q '{base:.baseRefName, files:(.files|length)}'
```

## Restack when a parent merges

**A squash-merged parent strands its children.** The child branch still holds the parent's
individual commits; `main` holds one commit that is none of them. A plain `git rebase main`
replays the parent's work a second time and conflicts on every line it touched. This repo
merges both ways — some PRs as merge commits, the recent ones squashed — so assume the squash
case.

Rebase onto the new base while excluding everything the parent already contributed. Take the
parent's old tip from GitHub, which keeps it after the merge:

```bash
OLD_PARENT=$(gh pr view <parent-pr> --json headRefOid -q .headRefOid)
git fetch origin
git rebase --onto origin/main "$OLD_PARENT" <child-branch>
gh pr edit <child-pr> --base main
git push --force-with-lease
```

`--onto` replays only the child's own commits, so it works whether the parent was squashed or
merge-committed. `--force-with-lease` refuses the push if someone else moved the branch.

Restack **bottom-up**: fix the lowest orphaned child first, then the one above it, so each
rebase runs against a parent that is already correct.

## Write the PR body

Use the four headings this repo already uses, and open with the stack position so a reviewer
knows what they are standing on:

```markdown
Phase 2 of 5. Based on `phase-1-data-layer` (#12), which must merge first.

## What prompted it
## What changed
## Verification
## Worth a reviewer's attention
```

Explain *why* a choice was made where the reason is not obvious from the diff — the decision
that was rejected, and the constraint that forced it. That is the bar the rest of this
codebase's comments hold to.

## Anti-patterns

| Thought | What to do |
|---|---|
| "The phases are related, so they belong in one PR" | Related is why they are a stack rather than separate branches. Split at the phase. |
| "I'll add this one thing to the current PR" | That thing belongs to a phase. Put it on that phase's branch. |
| "It reads better as one change" | It reads better to you, having written it. Size the PR for someone meeting it cold. |
| "I'll split it before opening the PR" | Cut the branches as you build. Splitting a finished branch means untangling commits that already interleave. |
| "The refactor is small, I'll fold it into the feature" | A refactor folded into a feature is the one thing a reviewer cannot verify separately. Bottom rung, own PR. |
| "Rebasing the child is conflicting everywhere" | The parent was squashed. Use `--onto` with the parent's old tip, above. |
