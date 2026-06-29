# React Skill

## When to use it

Use this skill for React components, frontend state, routing, styling, build tooling, accessibility, or browser-facing behavior.

## Useful commands

```bash
npm test
npm run lint
npm run build
npm run dev
pnpm test
pnpm run build
```

## Project conventions

- Inspect `package.json` before choosing npm, pnpm, yarn, or another tool.
- Follow existing component, styling, and state-management patterns.
- Keep UI changes focused and avoid replacing the design system.
- Prefer accessible markup and predictable keyboard behavior.

## Common traps

- Do not assume dependencies or scripts exist.
- Do not introduce a new framework, styling system, or icon library without a project reason.
- Do not leave text overflow, overlapping controls, or broken responsive states unchecked.
- Build commands and dev servers may require permission because they can take time or write artifacts.

## Done criteria

- The relevant package scripts are identified.
- Changed components follow existing project patterns.
- Build, lint, test, or a clearly scoped smoke check has been run when feasible.
- Any unverified browser behavior is called out.
