Cody Banks Roadmap — Planning, Memory, and Execution

Focus

Cody Banks already has a useful local coding-agent loop. The next improvement is not more tools first. The next improvement is separating context, intention, and action.

Memory is background context.

Roadmaps are active task state.

Execution is roadmap-following behavior.

The desired workflow is:

discuss → clarify → write roadmap → execute roadmap → update memory with durable lessons

Phase 15 — Project Memory

Make .cody/memory.md a first-class project knowledge file.

It should store durable project context, not temporary task plans.

Memory should include:

* stable project facts
* architectural decisions
* coding conventions
* user preferences
* known risks
* recurring warnings
* durable lessons learned from previous work

Memory should not include:

* full transcripts
* every tool result
* temporary plans
* speculative notes that are no longer relevant

Add commands:

/memory show
/memory add
/memory search
/memory prune

Cody should read memory automatically when starting a task, but it should update memory only when something durable has been learned.

Done when Cody can use memory as background context without confusing it for the active task plan.

Codex Result:
```
• Implemented Phase 15 project memory.

  Changed:

  - Added cody_banks/memory.py:1 with .cody/memory.md creation, read, add, search, and prune helpers.
  - Wired /memory show, /memory add, /memory search, and /memory prune into cody_banks/agent.py:224.
  - Cody now reads project memory into interactive task context and one-shot prompts via cody_banks/agent.py:324 and cody_banks/cli.py:48.
  - Changed /compact so it no longer writes transcript-style summaries into memory.
  - Added the initial .cody/memory.md:1 template.
  - Updated memory behavior docs in README.md:21 and system prompt guidance.

  Validated:

  - python -m compileall cody_banks passed.
  - Ran a smoke test covering memory creation, /memory add, /memory search, prompt inclusion, and /memory prune; passed.
```


Phase 16 — Roadmap Mode

Add a first-class planning workflow.

Cody should be able to inspect the project, ask clarifying questions, and write a task roadmap before making changes.

Add commands:

/roadmap
/roadmap latest
/roadmap new

Roadmaps should live under:

.cody/roadmaps/

Suggested filename format:

YYYYMMDD-HHMM-task-name.md

A roadmap should include:

# Goal
# Background
# Clarifying Questions
# Assumptions
# Files Likely Involved
# Steps
# Validation Plan
# Stop Conditions
# Memory Updates To Consider

In Roadmap Mode, Cody may:

* read files
* search files
* retrieve context
* inspect git state
* run safe inspection commands
* load relevant skills
* ask clarifying questions
* draft or revise the roadmap

In Roadmap Mode, Cody may not:

* edit project files
* create non-roadmap files
* delete files
* rename files
* apply patches
* run mutating shell commands

Done when Cody can turn a vague request into an inspectable roadmap saved under .cody/roadmaps/.

Codex Result:
```
• Implemented Phase 16 Roadmap Mode.

  Changed:

  - Added cody_banks/roadmap.py:1 for .cody/roadmaps/ paths, latest-roadmap lookup, timestamped filenames, slugging, and required-section normalization.
  - Added /roadmap, /roadmap latest, and /roadmap new TASK in cody_banks/agent.py:272.
  - Added restricted Roadmap Mode tool handling: read/list/search/retrieve context, git state, safe inspection shell commands, and skill loading via read_file.
  - Made retrieve_context optionally non-mutating so Roadmap Mode does not build .cody/index/ as a side effect.
  - Added .cody/roadmaps/.gitkeep.
  - Updated README and system prompt guidance for roadmaps as active task state.

  Validated:

  - python -m compileall cody_banks passed.
  - Smoke test passed for /roadmap new, roadmap-mode read_file, saved roadmap output, /roadmap latest, and rejection of mutating roadmap tools.
```


Phase 17 — Execute Roadmap

Add roadmap-following execution.

Add commands:

/execute latest
/execute path/to/roadmap.md

Execution Mode should read the roadmap, follow it step by step, and update progress as it works.

The agent should not re-plan from scratch unless the roadmap is wrong or incomplete.

During execution, Cody should:

* identify the active step
* inspect before editing
* make the smallest useful change
* validate according to the roadmap
* mark completed steps
* record deviations
* pause when assumptions break
* summarize changed files and validation results

Roadmap progress can be tracked directly inside the roadmap using checkboxes:

- [ ] Step 1
- [x] Step 2

Cody should stop and ask before continuing when:

* the roadmap conflicts with observed files
* a required file is missing
* the implementation requires a larger design change
* validation fails in a way not covered by the roadmap
* the next step would be destructive or risky

Done when Cody can execute a saved roadmap without losing the original intent.

Codex Result:
```
• Implemented Phase 17 Execution Mode.

  Changed:

  - Added /execute latest and /execute PATH in cody_banks/agent.py:443.
  - Execution Mode now reads a saved roadmap, finds the next unchecked checkbox step, executes only that step, and updates roadmap progress.
  - Added roadmap helpers in cody_banks/roadmap.py:43 for active-step detection, checkbox completion, path resolution, and execution notes.
  - Execution pauses and records a note when the model reports EXECUTION_STATUS: blocked, validation fails on the active step, the model errors, or the run exceeds 20 steps.
  - Successful steps are marked - [x] and get an # Execution Notes entry with summary, validation, and deviations.
  - Updated README and system prompt docs for /execute.

  Validated:

  - python -m compileall cody_banks passed.
  - Smoke test passed for /execute latest, checkbox progress, successful-step notes, blocked-step notes, and pause behavior.
```


Phase 18 — Automatic Skill Loading

Make skill loading part of roadmap creation and execution.

Cody already has markdown skills. The next step is selecting relevant ones automatically.

During roadmap creation, Cody should infer likely skills from the task.

Examples:

Python task → load python.md
Git task → load git.md
React task → load react.md
Local model task → load local_llm.md

The roadmap should record which skills were loaded and why.

During execution, Cody should load the skills named in the roadmap before making changes.

Do not build a complicated plugin system yet. Start with simple keyword and file-pattern matching.

Done when Cody can automatically load relevant skill files and use them as context while planning or executing.

Milestone — Deliberate Cody

Done when Cody can:

* remember durable project context
* create a roadmap from a vague request
* ask clarifying questions before coding
* save the roadmap as active task state
* execute the roadmap step by step
* load relevant skills automatically
* pause when the roadmap no longer matches reality
* update memory only with durable lessons

Design Principle

Memory is identity.

Roadmap is intent.

Execution is behavior.

Cody should not just respond to prompts. Cody should learn what the project is, decide what should happen next, write that decision down, and then follow it carefully.


Codex Result:
```
• Implemented Phase 18 automatic skill loading.

  Changed:

  - Added cody_banks/skill_loader.py:1 with simple keyword/file-pattern matching for python.md, git.md, react.md, and local_llm.md.
  - Roadmap creation now infers relevant skills, loads their markdown content into Roadmap Mode, and records them in a # Loaded Skills section.
  - Execution Mode now parses # Loaded Skills from the roadmap and reloads those skill files before running each active step.
  - Added roadmap helper support for inserting the loaded-skills record.
  - Updated README, skills README, and system prompt guidance for automatic skill loading.

  Validated:

  - python -m compileall cody_banks passed.
  - Smoke test passed for roadmap skill inference and # Loaded Skills recording.
  - Smoke test passed for execution-time skill reload into the model context.
```