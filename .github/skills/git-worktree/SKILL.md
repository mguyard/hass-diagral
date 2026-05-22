---
name: git-worktree
description: "Git Worktree: parallel working trees for isolated branch-level execution, debugging, and safe experimentation."
license: "See repository LICENSE"
user-invocable: false
---

# Git Worktree

## Overview

Git worktree allows attaching **multiple working trees** to a single repository. Each worktree operates on its own branch independently, enabling true parallel development without stashing, switching, or risking merge conflicts in the working directory.

In the context of this multi-agent workflow, worktrees are used **conditionally** — only when the standard file-ownership parallelization strategy is insufficient.

Use worktrees for **filesystem isolation** and `/delegate` for **session isolation**. They complement each other rather than replacing each other.

## When to Use This Skill

- Orchestrator needs to run parallel tasks that **must modify the same files** as independent features
- Debugger needs an **isolated reproduction environment** without disturbing ongoing work
- CoderSr is performing a **high-risk refactoring** that needs rollback safety
- Multiple independent features are being developed simultaneously and share core files

## When NOT to Use This Skill

- Tasks touch non-overlapping files (standard file-ownership is sufficient)
- Work is purely sequential
- Single-feature, single-branch workflows
- Simple bug fixes or minor changes

---

## 1. Core Commands Reference

### Create a Worktree

```bash
# Create a new worktree with a new branch
git worktree add <path> -b <new-branch-name> [<start-point>]

# Example: create a worktree for feature work
git worktree add ../project-feature-auth -b feature/auth main

# Create a worktree on an existing branch
git worktree add <path> <existing-branch>
```

### List Worktrees

```bash
git worktree list
# Output:
# /path/to/main-repo        abc1234 [main]
# /path/to/project-feature   def5678 [feature/auth]
```

### Remove a Worktree

```bash
# Remove after work is done
git worktree remove <path>

# Force remove (if worktree has uncommitted changes)
git worktree remove --force <path>
```

### Prune Stale Worktrees

```bash
# Clean up references to manually deleted worktrees
git worktree prune
```

---

## 2. Worktree Lifecycle (Orchestrator-Managed)

The Orchestrator is the **sole owner** of worktree lifecycle. Coding agents work within worktrees but do NOT create or remove them.

### Phase 1: Create

Orchestrator creates a worktree before delegating:

```bash
# Convention: sibling directory, descriptive name
git worktree add ../<project>-wt-<purpose> -b wt/<purpose> <base-branch>
```

**Branch naming convention:** `wt/<purpose>` (e.g., `wt/feature-auth`, `wt/debug-login-crash`, `wt/refactor-api-layer`).

**Path convention:** sibling directory `../<project>-wt-<purpose>`.

### Phase 2: Delegate

Orchestrator delegates the task to the coding agent with:

- The worktree path as the working directory
- The branch name for reference
- Clear scope of what to implement

### Phase 3: Agent Works & Commits

The coding agent:

1. Works **exclusively** within the delegated worktree path
2. Commits all changes before returning control
3. Does NOT push, merge, or modify other worktrees

### Phase 4: Merge

After agent completes and Reviewer approves:

```bash
# Orchestrator merges from main worktree
git merge wt/<purpose>

# Or cherry-pick specific commits
git cherry-pick <commit-hash>
```

### Phase 5: Cleanup (MANDATORY)

Orchestrator MUST clean up after merge:

```bash
git worktree remove ../<project>-wt-<purpose>
git branch -d wt/<purpose>
```

> **CRITICAL:** Never leave worktrees dangling. Every created worktree must be removed after its purpose is fulfilled.

---

## 3. Common Pitfalls

### Locked Worktrees

If a worktree path still exists but is locked:

```bash
git worktree unlock <path>
git worktree remove <path>
```

### Shared Refs

All worktrees share the same `.git` directory. This means:

- **Refs are shared** — branch names must be unique across all worktrees
- **A branch can only be checked out in ONE worktree at a time**
- Stash is shared across worktrees

### Submodules

If the project uses submodules, they must be initialized separately in each worktree:

```bash
cd <worktree-path>
git submodule update --init --recursive
```

### Dependencies

Each worktree has its own working tree — `node_modules`, build artifacts, virtual environments, etc. must be installed independently:

```bash
cd <worktree-path>
npm install    # or pip install, etc.
```

---

## 4. Patterns for Multi-Agent Use

### Pattern A: Parallel Feature Development

When two independent features must modify the same files (e.g., both touch `App.tsx`):

```
Main worktree:     stays on main branch (Orchestrator control)
Worktree A:        wt/feature-auth   → CoderSr works on auth
Worktree B:        wt/feature-dashboard → CoderSr works on dashboard
```

After both complete → Orchestrator merges sequentially, resolving conflicts if any.

### Pattern B: Isolated Bug Reproduction

Debugger needs a clean tree to reproduce without in-progress changes:

```
Main worktree:     feature work in progress
Worktree debug:    wt/debug-issue-42  → Debugger reproduces and fixes
```

After fix → merge back, remove worktree.

### Pattern C: Safe Refactoring

High-risk structural change that might need to be rolled back:

```
Main worktree:     stable state preserved
Worktree refactor: wt/refactor-api-v2 → CoderSr performs refactoring
```

If refactoring passes review → merge. If it fails → simply remove the worktree, no damage done.

### Pattern D: Worktree + `/delegate`

When a task is both long-running and likely to overlap with ongoing work:

1. Orchestrator creates the worktree first
2. the delegated/background session works only inside that worktree
3. durable outcomes are written back to `.agent-memory/` before the branch is closed
4. main orchestration still owns merge and cleanup

---

## 5. Cleanup Checklist

After every worktree session, Orchestrator must verify:

- [ ] All changes committed in worktree
- [ ] Changes merged or cherry-picked to target branch
- [ ] Worktree removed (`git worktree remove`)
- [ ] Worktree branch deleted (`git branch -d`)
- [ ] No stale entries (`git worktree prune`)

---

## 6. Orchestrator Decision Policy

Use this section when the Orchestrator is deciding whether to introduce a worktree.

### Use a Worktree When

At least one is true:

1. parallel tasks must touch overlapping files
2. risky refactor or rollback safety requires filesystem isolation
3. debugging needs a clean reproduction environment separate from in-flight work
4. Multi-Hive execution requires isolated branch ownership

### Do NOT Use a Worktree When

All are true:

1. file scopes are already disjoint
2. work can run sequentially without major delay
3. no isolation or rollback benefit exists

### Ownership Rules

1. Orchestrator alone creates, merges, and removes worktrees
2. delegated agents work only inside the provided worktree path
3. delegated agents do not create, remove, or merge worktrees
4. cleanup is mandatory after merge or abandonment
