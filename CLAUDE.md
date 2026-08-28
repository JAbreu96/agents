# agents

## Ship a feature as a stack

A feature whose plan has more than one phase ships as a **stack**: one PR per phase, each
based on the previous, only the bottom one on `main`. A five-phase plan is five PRs.

Follow `.claude/skills/stacked-pr/` when a plan has more than one phase, when a change is
heading past ~500 lines or ~10 files, or when a merged parent leaves its children to restack.
