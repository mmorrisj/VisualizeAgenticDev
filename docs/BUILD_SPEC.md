# Build Spec: Interactive Harness Training Site

This document is the complete brief for building an interactive, browser-based companion to the "What Is a Harness?" training course. Read all of it before starting. Work in the phases in section 9, and stop for review at the end of each phase.

---

## 1. Goal

Build a static website where students learn harness concepts by interacting with diagrams and simulations instead of reading. Each concept gets one interactive visual with a short explanation beside it. The written course (Markdown READMEs) stays the source of truth for content; the site makes the mechanisms visible.

**Audience:** developers new to AI-assisted coding tools. Do not refer to them as "beginners" anywhere in the site.

---

## 2. Hard constraints

These are non-negotiable. The site will be deployed on an air-gapped network.

| Constraint | What it means in practice |
|---|---|
| **No network access at runtime** | No CDNs, no web fonts, no analytics, no external images, no `fetch` to any remote host. Every asset ships in the repo |
| **No build step required to run** | The site must work by opening `index.html` through any static file server. Plain HTML, CSS, and JavaScript (ES modules are fine) |
| **No runtime dependencies** | No npm packages in the shipped site. No frameworks (React, Vue, D3, etc.). Hand-written SVG and DOM code only |
| **Works from a subpath** | All links and asset paths are relative, so it can be hosted at `https://internal-host/training/harness/` |
| **Content is editable without code changes** | All text, quiz questions, and simulation defaults live in JSON files under `content/` |
| **Accessible** | Keyboard operable, visible focus, color never the only signal, text alternatives for every diagram, respects `prefers-reduced-motion` |

Development tooling (linters, a test runner) is allowed only if it's optional, and the site must not depend on it to run. Prefer Python standard library scripts for any tooling.

---

## 3. Scope

### In scope: six interactive sections

1. Harness anatomy
2. Agent loop stepper
3. Context window simulator
4. Token growth explorer
5. Extension chooser
6. Knowledge checks (one per section, plus a final review)

### Out of scope

- Command-by-command references, attack walkthroughs, or prompt-injection payload examples. The written modules cover security topics; the site links to them instead of reproducing them.
- Any connection to a real model or real harness. All simulations use fixed, illustrative numbers.
- User accounts, progress tracking on a server, or anything that stores data off the student's machine. `localStorage` may remember which sections a student completed; wrap every access in `try/catch` and keep the site fully functional without it.

---

## 4. Repository layout

```text
harness-site/
├── index.html                 # landing page: course map + section cards
├── sections/
│   ├── anatomy.html
│   ├── loop.html
│   ├── context.html
│   ├── tokens.html
│   ├── extensions.html
│   └── review.html
├── assets/
│   ├── css/site.css           # design tokens + layout
│   └── js/
│       ├── common.js          # nav, theme, progress, content loading
│       ├── anatomy.js
│       ├── loop.js
│       ├── context.js
│       ├── tokens.js
│       ├── extensions.js
│       └── quiz.js            # shared quiz component
├── content/
│   ├── anatomy.json
│   ├── loop.json
│   ├── context.json
│   ├── tokens.json
│   ├── extensions.json
│   └── quizzes.json
├── tools/
│   ├── serve.py               # python3 tools/serve.py -> http://127.0.0.1:8000
│   └── check.py               # offline validation (section 8)
└── README.md                  # how to run, edit content, and deploy
```

Note: browsers block `fetch` of local JSON from `file://` URLs. The README must tell instructors to use `tools/serve.py` (a thin wrapper around `http.server`) or any internal web server.

---

## 5. Design system

- **Tokens on `:root`:** background, surface, text, muted text, border, accent, accent-2, success, warning. Provide a dark theme under `@media (prefers-color-scheme: dark)` and a manual toggle (`data-theme` on `<html>`).
- **Fonts:** system font stacks only (`system-ui, …` for text, `ui-monospace, …` for code). No downloaded fonts.
- **Layout:** each section page is a two-column layout on wide screens (visual left, explanation right) and a single column below 900px. No horizontal scrolling at 360px width.
- **Visual language:** consistent across sections. The model is always drawn the same way, the harness the same way, and tool results the same color everywhere they appear.
- **No emoji or decorative icon characters.** Use simple SVG shapes if a symbol is needed, with text labels beside them.
- **Motion:** short transitions (under 300ms) to show cause and effect. Disable all animation when `prefers-reduced-motion: reduce` is set.

---

## 6. Section specifications

Each section page has the same structure:

1. A one-sentence statement of the concept.
2. The interactive visual.
3. A side panel that explains what the student is seeing and updates as they interact.
4. A "Go deeper" link to the matching written module (relative link, path configurable in `content/*.json`).
5. A short knowledge check (section 6.6).

### 6.1 Harness anatomy

**Concept:** the model predicts text; the harness turns text into work.

**Visual:** a central model node surrounded by the six harness components: Instructions, Tools, Context, Permissions, Memory, Interface. A "You" node sits outside the harness boundary; "Your files, shell, APIs" sits outside on the other side.

**Interactions:**
- Clicking a component highlights it and fills the side panel with: what it does, why it matters, and which module covers it.
- A toggle "Show model only" fades out every component, leaving the model alone with no path to files or tools, to make the point that the model cannot act by itself.

**Content (`anatomy.json`):** one entry per component with `id`, `label`, `what`, `why`, `module_link`.

**Acceptance:** all six components reachable by keyboard (Tab, Enter); the panel's content is announced via an `aria-live="polite"` region.

### 6.2 Agent loop stepper

**Concept:** the model is stateless; the harness re-sends the whole conversation on every request.

**Visual, two parts:**
- A loop diagram with four stages: You ask, Model decides, Harness runs the tool, Result returns. The active stage is highlighted.
- A stacked "request" bar showing what is sent on the current request: system prompt, tool definitions, and each message, with tool results in their own color. The bar grows as the session continues.

**Interactions:**
- **Next** and **Back** buttons step through a scripted session. Use the practice-app investigation as the script: read the test file, run the tests, search for the function, read the source file, report the finding. Store the steps in `loop.json` with a label and a token size for each piece.
- At each step, the side panel explains what happened and shows the running request size.
- A **"What does the model see?"** button opens a panel listing every item in the current request, in order.

**Acceptance:** the request size shown at each step matches the sum of the items in the "What does the model see?" list. Stepping back restores the previous state exactly.

### 6.3 Context window simulator

**Concept:** fixed overhead is paid on every request, tool results accumulate, and compaction loses detail.

**Visual:** a horizontal context window with a visible limit line. Segments: harness system prompt, tool definitions, instructions file, conversation, tool results.

**Controls (sliders, each with a numeric readout):**
- Instructions file size
- Number of tool definitions (stands in for MCP servers added)
- Average tool result size
- Number of steps

**Behavior:**
- As steps increase, tool-result segments append. When total size crosses 80% of the limit, compaction runs: the oldest tool results collapse into a small "summary" block, with a brief visual marker. Count compactions and show the count.
- A line below states, in plain language, how many times the fixed overhead was sent and its total cost in tokens.

**Presets (buttons):** "Short instructions file", "Bloated instructions file", "Broad request". These match the Module 3 lab (bloated file roughly 5x the short one).

**Model:** use simple, documented arithmetic in `context.js`, with defaults in `context.json`. Include a comment block explaining every formula. Numbers are illustrative; label the visual "Illustrative numbers."

**Acceptance:** with the "Bloated instructions file" preset, the overhead line shows a larger total than "Short instructions file" for the same number of steps. Compaction never lets the total exceed the limit.

### 6.4 Token growth explorer

**Concept:** total input over a session grows much faster than the final context size, because every request carries everything before it.

**Visual:** a bar chart, one bar per request, bar height equal to that request's input tokens. A running-total line overlays it. Hand-drawn SVG, with labeled axes.

**Controls:**
- Session type: **Focused** (5 requests) or **Broad** (15 requests). Defaults taken from Module 7's example: focused ends near 1,200 tokens of context with about 4,300 total input; broad ends near 2,000 with about 21,000 total.
- **Caching** toggle: splits each bar into "processed fresh" and "read from cache." When on, show a single cache-miss bar partway through, with a tooltip explaining an idle gap broke the cache.

**Readouts:** final context size, total input, and the ratio between them.

**Acceptance:** each bar has an accessible label (request number and token count); the chart has a text summary for screen readers; the ratio readout updates when the session type changes.

### 6.5 Extension chooser

**Concept:** instructions files, skills, subagents, hooks, MCP servers, and plugins differ in when they load, what they cost, who triggers them, and whether they're guaranteed to run.

**Part A, decision flow:** a clickable version of the Module 5 decision chart. The student answers one question at a time (buttons for Yes or No); the path they took stays visible. The final node names the mechanism and shows its trade-offs.

Questions, in order:
1. Must it happen every time, regardless of what the model decides? (Yes: Hook or permission rule)
2. Is it access to an external system or data? (Yes: go to 3; No: go to 4)
3. Does a good command-line tool already exist for it? (Yes: use the CLI and document it; No: MCP server)
4. Is it a fact or constraint relevant to nearly every task? (Yes: instructions file)
5. Does it produce lots of output, or need an unbiased view? (Yes: subagent; No: skill)
6. After any result: Sharing it with a team? (Yes: package as a plugin)

**Part B, comparison grid:** a table of the six mechanisms against five attributes: when it loads, context cost, who triggers it, deterministic, runs code. Clicking a mechanism highlights its column; clicking an attribute highlights its row.

**Part C, scenario practice:** the seven design-exercise scenarios from Module 5 as cards. The student picks a mechanism for each; feedback explains the recommended answer.

**Acceptance:** the decision flow can be restarted at any point; every path ends at a result; scenario feedback is shown in text, not only by color.

### 6.6 Knowledge checks

A shared quiz component (`quiz.js`) driven by `quizzes.json`.

- Multiple choice, one question at a time, with an explanation shown after each answer.
- Each section page ends with 3 to 4 questions; `review.html` has a mixed set drawn from all sections.
- Correct and incorrect states use text ("Correct" / "Not quite") plus color.
- Draw questions from the "Check your understanding" sections of the written modules. Keep them conceptual.

---

## 7. Landing page

- Title, a two-sentence description, and the course map: six section cards in recommended order, each with a one-line summary.
- A link to the written course for instructors.
- If `localStorage` is available, mark completed sections. "Completed" means the section's knowledge check was finished.

---

## 8. Quality checks

Write `tools/check.py` (Python standard library only). It must:

1. Parse every JSON file in `content/` and validate required keys for each file.
2. Confirm every relative link and asset reference in the HTML files points to an existing file.
3. Fail if any HTML, CSS, or JS file contains `http://` or `https://`, except inside `content/*.json` links back to the written course, if configured as relative.
4. Fail if any file contains emoji or pictographic characters, or the word "beginner."
5. Confirm every `<img>` has `alt`, every inline `<svg>` has a `role="img"` with an accessible name or is marked decorative, and every button has a text label.

Manual checks before each phase review:

- Run through every section using only the keyboard.
- Test at 360px, 768px, and 1280px widths.
- Test light and dark themes and reduced motion.
- Load the site with networking disabled and confirm nothing is missing.
- Test in the browsers your network approves.

If Playwright and a browser are available offline in your environment, browser tests are welcome, but `check.py` and the manual checklist are the required minimum.

---

## 9. Build phases

Stop after each phase and summarize what changed, what's left, and any deviations from this spec.

| Phase | Deliverable | Done when |
|---|---|---|
| 1 | Skeleton: layout, design tokens, theme toggle, navigation, `serve.py`, `check.py`, landing page with placeholder cards | `check.py` passes; every page loads offline |
| 2 | Harness anatomy and agent loop stepper | Section 6.1 and 6.2 acceptance criteria met |
| 3 | Context window simulator and token growth explorer | Section 6.3 and 6.4 acceptance criteria met |
| 4 | Extension chooser | Section 6.5 acceptance criteria met |
| 5 | Quiz component, all knowledge checks, review page, progress marking | Section 6.6 and 7 met |
| 6 | Polish: accessibility pass, responsive pass, README for instructors | Full manual checklist passes |

Commit at the end of each phase with a message describing the phase. Keep each commit focused.

---

## 10. Working rules for the agent

- Ask before adding any dependency, file outside the layout in section 4, or feature outside section 3.
- Keep every file readable by an instructor: short functions, comments that explain *why*, no minified code.
- Never invent statistics. Use the illustrative numbers given here and label them as illustrative.
- If anything in this spec conflicts with itself or is unclear, stop and ask rather than guess.
- When a phase is done, run `python3 tools/check.py` and report its output.

---

## 11. Source material

The written course (the `harness-course` folder) is the content source. Relevant files:

| Site section | Source |
|---|---|
| Harness anatomy | `README.md` sections 2 and 4 |
| Agent loop | `modules/01-build-a-harness/README.md`; `mini-harness/scenarios/investigate.json` for the step script |
| Context window | `modules/03-context-engineering/README.md` |
| Token growth | `modules/07-token-observability/README.md` |
| Extensions | `modules/05-extensibility/README.md` sections 1 and 7 |
| Knowledge checks | "Check your understanding" in each README |

Copy the course folder into the repo under `course/`, or give the agent access to it, before starting Phase 2.
