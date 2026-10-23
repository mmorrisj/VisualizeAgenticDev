# Build Spec: Interactive Harness Training Site

**Version 2.** Changes from v1: the site is now an *explorable explanation*. A shared visual world runs through every section, tokens are drawn as physical blocks, and each section opens with a scroll-driven narrative before its sandbox. v1 defects are fixed (SVG namespace check, compaction edge cases, emoji detection, decision-flow mapping). See the changelog in section 12.

This document is the complete brief for building an interactive, browser-based companion to the "What Is a Harness?" training course. Read all of it before starting. Work in the phases in section 9, and stop for review at the end of each phase.

---

## 1. Goal

Build a static website where students learn harness concepts by watching and manipulating visuals instead of reading. The bar is a visually compelling *explorable explanation*, in the tradition of Bartosz Ciechanowski, Red Blob Games, and Distill: the visual carries the explanation, and the student can poke at it. This is not a game. There are no points, levels, or timers. The written course (Markdown READMEs) stays the source of truth for content; the site makes the mechanisms visible.

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
| **Content is editable without code changes** | All explanatory text, narrative steps, quiz questions, and simulation defaults live in JSON files under `content/`. Page chrome (navigation labels, button text) may live in HTML |
| **Accessible** | Keyboard operable, visible focus, color never the only signal, text alternatives for every diagram, respects `prefers-reduced-motion` |

Development tooling (linters, a test runner) is allowed only if it's optional, and the site must not depend on it to run. Prefer Python standard library scripts for any tooling.

---

## 3. Scope

### In scope: eight interactive sections

1. Harness anatomy
2. Agent loop stepper
3. Context window simulator
4. Token growth explorer
5. Extension chooser
6. Inside an extension (section 6.7)
7. Flow simulations: permissions, verification, network/data
8. Knowledge checks (one per section, plus a final review)

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
│   ├── _style.html            # design-language reference page (section 5.1)
│   ├── anatomy.html
│   ├── loop.html
│   ├── context.html
│   ├── tokens.html
│   ├── extensions.html
│   ├── inside-extensions.html
│   ├── flows.html
│   └── review.html
├── assets/
│   ├── css/site.css           # design tokens + layout
│   └── js/
│       ├── common.js          # nav, theme, progress, content loading
│       ├── scene.js           # shared visual world + token-block primitives
│       ├── scrolly.js         # links narrative scroll steps to scene states
│       ├── anatomy.js
│       ├── loop.js
│       ├── context.js
│       ├── tokens.js
│       ├── extensions.js
│       ├── inside-extensions.js
│       ├── flows.js
│       ├── flow-model.js
│       └── quiz.js            # shared quiz component
├── content/
│   ├── site.json              # landing copy, section order, card summaries
│   ├── anatomy.json
│   ├── loop.json
│   ├── context.json
│   ├── tokens.json
│   ├── extensions.json
│   ├── inside-extensions.json
│   ├── flows.json
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
- **Layout:** desktop only. Students use the course on desktop browsers, so optimize for 1280px and wider: two-column layouts (visual left, explanation right) that use the available width. Phones and tablets are out of scope; narrower windows need not be optimized.
- **Visual language:** consistent across sections. The model is always drawn the same way, the harness the same way, and tool results the same color everywhere they appear.
- **No emoji or decorative icon characters.** Use simple SVG shapes if a symbol is needed, with text labels beside them.
- **Motion:** two kinds, with different rules.
  - *UI feedback* (hover, focus, selection, button press): under 300ms.
  - *Explanatory animation* (tokens flowing, stacking, compacting): up to about 2s, always pausable and replayable, and driven by step state so it can be scrubbed with Next and Back.
  - With `prefers-reduced-motion: reduce`, explanatory animations jump straight to their end state (or crossfade). Never show a blank or a half-finished state.
- **Motion has meaning.** Things move only to show cause and effect: data flowing, accumulating, being compressed. No decorative motion.

### 5.1 One shared visual world

Every section draws the same scene and zooms into a different part of it. Students build one mental model, not six.

| Element | How it is always drawn |
|---|---|
| Model | A sealed rounded box in the center. It has no connections of its own |
| Harness | A ring around the model; components sit on the ring |
| You | A node outside the ring, on the left |
| Your files, shell, APIs | A node outside the ring, on the right |
| Token | A small square block. All sizes in the course are shown as blocks, at a fixed tokens-per-block scale stated on screen |
| Request | A row of blocks travelling into the model |
| Context window | A container with a visible limit line |
| Compaction summary | A single hatched tile that replaces the blocks it summarizes |

Each content role has one color **and** one secondary cue (pattern or label), used identically everywhere: system prompt, tool definitions, instructions file, user message, model message, tool result, summary.

`sections/_style.html` is the living reference for this world. It shows every primitive in light and dark themes, plus a short narrative demo. It is built in Phase 1 and approved before any section work starts.

---

## 6. Section specifications

Each section page has the same structure:

1. A one-sentence statement of the concept.
2. **Guided narrative.** Short text steps scroll past while the visual stays pinned (sticky). Each step sets a scene state. A Next and Back stepper mirrors the scroll steps and stays in sync with them. On narrow screens the visual pins to the top and the text scrolls beneath it. Steps live in the section's JSON as `steps[]`, each with `text` and a `state` object the section script understands.
3. **Predict, then reveal** (optional, at most one or two per section). Before a key animation, ask an unscored question ("How big will request 15 be?"), then show the answer.
4. **Sandbox.** The full interactive visual, described below, with a side panel that explains what the student is seeing and updates as they interact.
5. A "Go deeper" link to the matching written module (relative link, path configurable in `content/*.json`).
6. A short knowledge check (section 6.6).

Every section also names one **signature moment**: the single visual the student should remember. Design it deliberately.

### 6.1 Harness anatomy

**Concept:** the model predicts text; the harness turns text into work.

**Signature moment:** the page opens on the full harness, working. As the student scrolls, the components fall away one by one until the model is left alone, emitting text into nothing. Then the components snap back.

**Visual:** a central model node surrounded by the six harness components: Instructions, Tools, Context, Permissions, Memory, Interface. A "You" node sits outside the harness boundary; "Your files, shell, APIs" sits outside on the other side.

**Interactions:**
- Clicking a component highlights it and fills the side panel with: what it does, why it matters, and which module covers it.
- A toggle "Show model only" fades out every component, leaving the model alone with no path to files or tools, to make the point that the model cannot act by itself.

**Content (`anatomy.json`):** one entry per component with `id`, `label`, `what`, `why`, `module_link`.

**Acceptance:** all six components reachable by keyboard (Tab, Enter); the panel's content is announced via an `aria-live="polite"` region.

### 6.2 Agent loop stepper

**Concept:** the model is stateless; the harness re-sends the whole conversation on every request.

**Signature moment:** every turn, the whole conversation visibly travels back into the model as a growing train of blocks. By step 5 the train is long, and the re-sending is obvious.

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

**Signature moment:** tool results pour into the window. At 80% the oldest blocks are squeezed into a hatched summary tile, and a few fine-detail blocks visibly crumble away. Compaction loses detail, and the student sees it happen.

**Visual:** a horizontal context window with a visible limit line. Segments: harness system prompt, tool definitions, instructions file, conversation, tool results.

**Controls (sliders, each with a numeric readout):**
- Instructions file size
- Number of tool definitions (stands in for MCP servers added)
- Average tool result size
- Number of steps

**Behavior:**
- As steps increase, tool-result segments append. Before each append, if the new total would cross 80% of the limit, compaction runs first: the oldest tool results collapse into a small "summary" block, with a brief visual marker. Count compactions and show the count.
- A line below states, in plain language, how many times the fixed overhead was sent and its total cost in tokens.
- **Edge cases:**
  - If one tool result is larger than the space left after compaction, it is truncated to fit, and the visual marks it "truncated".
  - If fixed overhead alone (system prompt, tool definitions, instructions file) exceeds the limit, the simulation does not start. It shows "Overhead exceeds the context window", which is itself a teaching point.

**Presets (buttons):** "Short instructions file", "Bloated instructions file", "Broad request". These match the Module 3 lab (bloated file roughly 5x the short one).

**Model:** use simple, documented arithmetic in `context.js`, with defaults in `context.json`. Include a comment block explaining every formula. Numbers are illustrative; label the visual "Illustrative numbers."

**Acceptance:** with the "Bloated instructions file" preset, the overhead line shows a larger total than "Short instructions file" for the same number of steps. Compaction never lets the total exceed the limit, including with every slider at its maximum.

### 6.4 Token growth explorer

**Concept:** total input over a session grows much faster than the final context size, because every request carries everything before it.

**Signature moment:** focused and broad sessions run side by side. Each request's blocks drop into a "total paid" pile underneath. The broad pile towers over the focused one, while the two final context sizes look almost the same.

**Visual:** a bar chart, one bar per request, bar height equal to that request's input tokens. A running-total line overlays it. Hand-drawn SVG, with labeled axes.

**Controls:**
- Session type: **Focused** (5 requests) or **Broad** (15 requests). Defaults taken from Module 7's example: focused ends near 1,200 tokens of context with about 4,300 total input; broad ends near 2,000 with about 21,000 total.
- **Caching** toggle: splits each bar into "processed fresh" and "read from cache." Cached blocks are drawn dimmed. When on, show a single cache-miss bar partway through, where the blocks visibly re-solidify, with a tooltip explaining that an idle gap broke the cache.

**Readouts:** final context size, total input, and the ratio between them.

**Acceptance:** each bar has an accessible label (request number and token count); the chart has a text summary for screen readers; the ratio readout updates when the session type changes.

### 6.5 Extension chooser

**Concept:** instructions files, skills, subagents, hooks, MCP servers, and plugins differ in when they load, what they cost, who triggers them, and whether they're guaranteed to run.

**Signature moment:** a timeline scrubber plays one session, and each mechanism lights up on the harness ring when it activates. The hook fires every time; the skill fires only when the model picks it.

**Part A, decision flow:** a clickable version of the Module 5 decision chart. The student answers one question at a time (buttons for Yes or No); the path they took stays visible. The final node names the mechanism and shows its trade-offs.

Questions, in order:
1. Must it happen every time, regardless of what the model decides? (Yes: Hook or permission rule)
2. Is it access to an external system or data? (Yes: go to 3; No: go to 4)
3. Does a good command-line tool already exist for it? (Yes: use the CLI, documented in the instructions file or a skill. The result node links to both columns in Part B. No: MCP server)
4. Is it a fact or constraint relevant to nearly every task? (Yes: instructions file)
5. Does it produce lots of output, or need an unbiased view? (Yes: subagent; No: skill)
6. After any result, including Hook or permission rule: Sharing it with a team? (Yes: package as a plugin)

**Part B, comparison grid:** a table of the six mechanisms against five attributes: when it loads, context cost, who triggers it, deterministic, runs code. Clicking a mechanism highlights its column; clicking an attribute highlights its row.

**Part C, scenario practice:** the seven design-exercise scenarios from Module 5 as cards. The student picks a mechanism for each; feedback explains the recommended answer.

**Acceptance:** the decision flow can be restarted at any point; every path ends at a result; scenario feedback is shown in text, not only by color.

### 6.6 Knowledge checks

A shared quiz component (`quiz.js`) driven by `quizzes.json`.

- Multiple choice, one question at a time, with an explanation shown after each answer.
- Each section page ends with 3 to 4 questions; `review.html` has a mixed set drawn from all sections.
- Correct and incorrect states use text ("Correct" / "Not quite") plus color.
- Draw questions from the "Check your understanding" sections of the written modules. Keep them conceptual.


### 6.7 Inside an extension

Placed after the extension chooser (section 6.5) in page order: section 6 of 8, before flow simulations and the final review. The chooser answers *which mechanism*; this section answers *what happens inside the harness when it runs*. It covers MCP servers, skills, subagents, and plugins. Hooks appear only as a plugin component.

**Concept:** each mechanism changes a different part of the request. An MCP server adds tool definitions and a separate process; a skill adds a short description now and its body later; a subagent runs a second conversation in its own context; a plugin brings all of them at once.

**Signature moment:** one session, opened up four ways. In every lens the main request bar is the same; what changes is which blocks the mechanism adds, when they arrive, and whether they stay on every later request. The student should leave able to point at a request and say which blocks each mechanism put there.

**The session.** One task, used by all four lenses: *"The tests are failing. Find out why, fix it, add a regression test, and check whether any user has an empty password."* In order: the skill triages the failure; the MCP server answers the password question; the model edits the code and adds a test (the hook checks both edits before they happen); the subagent reviews the new test. The harness has the `practice-toolkit` plugin from Module 5 installed: the `practice-test-triage` skill, the `test-reviewer` subagent, the `no_test_weakening` hook, and the `practice-db` MCP server.

**Visual:** a widescreen scene laid out left to right: You, Harness, Model. The main context is drawn as a stacked request bar using the shared token blocks and content roles (section 5.1), with two new roles: `skill` and `subagent`, each with its own color and a non-color marker. Right of the harness, an "outside the model" lane holds the `practice-db` server process, the `skills/` folder, and the subagent's own context window. A meter under the scene shows two numbers for the selected request: **on every request** and **on use**.

**Lenses:** four tabs (ARIA tabs pattern, Left/Right between tabs), each a Play tour with Play/Pause, Back, Next, and a restart. Space plays or pauses; Left and Right step. Each step has short text, a scene state, and an optional wire payload shown in a panel beside the scene. Steps are listed below; wording lives in content.

*MCP lens*
1. Session start: the harness launches the server as a subprocess. A pipe appears between the harness and the process, labelled stdin and stdout.
2. `initialize` and its reply travel the pipe as packets; the wire panel shows the real messages. The reply's `instructions` string is shown with a note that some harnesses add it to context.
3. `tools/list`: three tool definitions return and drop into the request bar as a tools block (measured size). The block stays in every later request; the meter's "on every request" number rises.
4. The model asks for `run_select`. The harness checks permission for `mcp__practice-db__run_select`, then sends `tools/call` down the pipe.
5. The result text returns and enters the conversation as a tool result, the same way a file read does.
6. A `DELETE` is attempted; the server refuses with `isError: true`. The refusal text still enters the model's context. Text explains the two layers: the harness decides whether the call may happen; the server decides what the call can do.
7. What runs as you: the server is a separate process with its own access, usually outside the command sandbox.

*Skill lens*
1. Session start: only the skill's name and description enter the request bar, as a thin skill block (measured size). The body stays on disk.
2. The user's task matches the description; the model picks the skill.
3. The body unfolds into the request bar (measured size). Text: the description is paid on every request; the body only from now on.
4. The procedure tells the model to run `failures.py`. The script runs outside the model, through the agent's normal shell tool and permissions.
5. Side by side: the full test output (measured characters and tokens) and the two lines the script prints. Only the two lines enter the context; the full output is shown shrinking into them.
6. What runs as you: the script runs with the agent's permissions, inside the sandbox if one is on.

*Subagent lens*
1. After the regression test is added, the main conversation delegates a review of the test change to `test-reviewer` (its description says to use it after any edit under `tests/`).
2. A second context window splits off the main one. It starts with its own system prompt (the agent file's body), the delegated task, and only Read, Grep, and Glob; Edit and Bash are drawn locked.
3. The subagent makes its own requests; its own meter grows while the main meter does not move.
4. The subagent finishes; its window collapses into one summary block that drops into the main conversation. The meter shows how much the main context grew (the summary) against how much the subagent read.
5. Text: the subagent never saw the main conversation, which is the point of using one for review; and its read-only tool list is least privilege.

*Plugin lens*
1. A `practice-toolkit` package (its `plugin.json` shown in the wire panel) opens into four components.
2. Each component flies to where it lives: the skill description and the subagent description into the request bar; the hook onto the harness's `PreToolUse` event, with no context cost; the MCP server into the outside lane as a running process, whose tool definitions join the request when it starts.
3. The meter shows the plugin's always-on cost using the site's estimator, next to the figure Claude Code reported for the same plugin in Module 5, labelled as such.
4. The hook fires before each `Edit` and `Write`, including the regression test; it lets this one through because it adds an assertion rather than removing one. The harness, not the model, runs it, and it adds nothing to context.
5. An "Enable plugin" toggle removes every block and process the plugin added. Text: an enabled plugin costs its descriptions on every request in every session, used or not.
6. What runs as you: the hook and the local MCP server run as you, usually outside the sandbox; the plugin can change when it updates.

**Sandbox, the cost ledger:** below the lenses. Toggles for the MCP server, the skill, the subagent, and the plugin (enabling the plugin enables all its parts). A chart shows each request of the session as a stacked bar split into always-on blocks and on-use blocks, with running totals for the session's total input. Selecting a bar shows that request's parts in the panel. With the subagent off, the test review happens in the main conversation and everything it reads lands in the main context; with it on, only its summary does. The ledger shows both.

**Content (`inside-extensions.json`):** `concept`, `module_link` (Module 5), `source_note`, `task`, `lenses` (each with `id`, `label`, `intro`, `steps` of `{text, state, wire?}`), `components` (each with measured `always_tokens`, `on_use_tokens`, and its source file), `wire` (the recorded MCP exchange, verbatim), `triage` (full-output and condensed sizes), `ledger` (the session's requests and the parts each mechanism contributes), and `claude_code_reported` (the Module 5 figures, cited).

**Data:** sizes and payloads come from running the course's own examples: `mcp_probe.py` for the MCP exchange and the tool-definition size, the skill and agent files' own text, `failures.py` against a fresh practice-app copy, and the plugin's manifest files. Token counts use the course harness's estimator (about 4 characters per token, `estimate_tokens` in `mini-harness/backends.py`), the same as every other section. The course harness cannot run MCP servers, skills, or subagents, so the **order** of the session is scripted; the page says so in its source note ("real messages and sizes, scripted sequence"). Claude Code's own figures for the plugin (about 80 and 190 tokens for the skill, 119 always-on) differ from the estimator's; they appear once, labelled as Claude Code's count.

**Motion:** this section uses more motion than the others, because the mechanisms are about movement between places: packets on the pipe, the skill body unfolding, the subagent window splitting and collapsing, the plugin's components flying to their places. Use SVG and the Web Animations API, no libraries. Every effect explains a step and follows the explanatory-motion rules in section 5 (up to about 2s, pausable, driven by step state); with reduced motion, each step jumps to its end state. Wire payloads may type out line by line; with reduced motion they appear at once.

**Knowledge check:** four questions, conceptual, drawn from Module 5's labs: what `tools/list` adds to every request; which part of a skill is always in context; what returns to the main conversation from a subagent; what an enabled but unused plugin costs. One joins the final review's mixed set.

**Out of scope here:** prompt-injection payloads (section 3). The MCP lens notes that tool descriptions are text written by the server's author and go into the model's context, and links to Module 5's security review instead of showing an attack.

**Acceptance:**
- All four lenses play end to end with the mouse and with the keyboard alone; Back restores a previous step exactly.
- In every step, the request bar's blocks sum to the meter's numbers; `check.py` validates the sums, that every step's state references known blocks, and that the ledger's totals match its parts.
- Every wire payload shown is copied from a recorded run of the course examples, not retyped.
- With reduced motion, no step shows a blank or half-drawn scene.
- Every scene has an accessible name that describes its current state; lens and step changes are announced in an `aria-live="polite"` region.
- New roles (`skill`, `subagent`) are distinguishable without color.
- Locked subagent tools and the plugin toggle state are shown in text as well as visually.

---

### 6.8 Flow simulations

One section with three lenses closes the visual coverage gaps in Modules 2, 4,
and 6. The shared model box and harness component styling remain consistent.
All scenarios are scripted teaching models, with no command execution or remote
connections. Content, control labels, defaults, and explanations live in
`content/flows.json`; `flow-model.js` derives traces and `flows.js` renders them.

- **Permissions:** the signature moment is an approved shell request that still
  fails at the network sandbox. Follow hooks, deny, ask, allow, human decision,
  execution, result, and return to the model. Toggle rules and choose a test edit,
  test run, or conceptual shell network call. Match the reference harness's
  precedence; a blocked request never visits execution. Do not teach bypass payloads.
- **Verification:** the signature moment is the same green test summary for a
  real fix and a weakened assertion. Compare the source/test diff, then keep the
  test and remove the implementation fix. Acceptance needs both checks; observed
  weakening causes rejection; missing evidence remains incomplete.
- **Network/data:** the signature moment is a denied public connection alongside
  retained local and internal file-body copies. Toggle model routing, egress,
  nonessential traffic, and body logging at gateway, endpoint, transcript, and
  internal telemetry. Show copies only after their branch is reached, distinguish
  transport from retention, and never imply that body logging is the only data risk.

Each lens opens with a complete live route, two experiment situations, and a
question to investigate. Gates and destinations are operable controls, bound to
the same settings as the sidebar. Changes immediately rebuild the route and
compare before/after outcomes. If a setting is irrelevant to the current route,
state that the outcome stayed the same. Preserve keyboard focus across redraws.
All explanatory copy, situations, settings, and control-state labels live in JSON.

Replay route provides a short, pausable/resumable animation of the selected
setup. Live view returns to the full outcome. Evidence, individual stops, and
Back/Next controls live in an optional inspection panel. Tabs follow the ARIA
keyboard pattern; diagram controls support Enter/Space, with visible focus and
state labels that describe their actual effect (for example, Network isolated).
Reduced motion draws complete states without packet animation.
Include four knowledge questions spanning the three lenses and one in final review.
Validate branch precedence, evidence decisions, unreachable endpoint logging, and
retained-copy state with automated tests, plus both themes and desktop widths.

---

## 7. Landing page

- Title, a two-sentence description, and the course map: eight section cards in recommended order, each with a one-line summary. Landing copy and card text come from `content/site.json`.
- An interactive rendering of the shared visual world (section 5.1) as the hero: selecting the model or one of the six components updates an adjacent explanation, reusing `anatomy.json`. Controls work with mouse, Enter, and Space, with visible focus and a text selection state.
- Course-map cards name an action students can try in each existing section.
- A curriculum explorer pairs all seven written modules with an existing visual, a prediction or investigation prompt, and a written lab. Coverage labels distinguish direct simulations from related visuals; no Python or network lab executes in the browser. Module copy and links live in `site.json`.
- Acceptance: all seven choices update the module panel and its two links; every link resolves from a hosted subpath; diagram selection and module choice work without local storage, with reduced motion, and in both themes at 1280, 1440, and 1920px. Dedicated hard-control, verification, and network simulations are provided by section 6.8.
- A link to the written course, placed in the footer.
- Instructor-facing material (instructor notes, the design-language page, build or source notes) is never displayed prominently to students. It stays in the README, the repository, or a quiet footnote. Files named `*INSTRUCTOR*` in the course are not published with the site.
- If `localStorage` is available, mark completed sections. "Completed" means the section's knowledge check was finished.

---

## 8. Quality checks

Write `tools/check.py` (Python standard library only). It must:

1. Parse every JSON file in `content/` and validate required keys for each file.
2. Confirm every relative link and asset reference in the HTML files points to an existing file.
3. Fail if any HTML, CSS, JS, or JSON file contains `http://` or `https://`. The only exceptions are the XML namespace URIs needed to build SVG from JavaScript (`http://www.w3.org/2000/svg`, `http://www.w3.org/1999/xlink`, `http://www.w3.org/1999/xhtml`). Links to the written course must be relative.
4. Fail if any file contains emoji or pictographic characters, or the word "beginner." Python's `unicodedata` does not expose emoji properties, so detect them with an explicit list of codepoint ranges (pictographs, dingbats, symbols, variation selector 16, zero-width joiner).
5. Confirm every `<img>` has `alt`, every inline `<svg>` has a `role="img"` with an accessible name or is marked decorative, and every button has a text label.
6. Confirm every relative `import` in the JS files points to an existing file.

SVG drawn at runtime by JavaScript cannot be checked statically; `scene.js` helpers must take a label and set `role` and `aria-label`, or mark the element decorative.

Manual checks before each phase review:

- Run through every section using only the keyboard.
- Test at 1280px, 1440px, and 1920px widths.
- Test light and dark themes and reduced motion.
- Load the site with networking disabled and confirm nothing is missing.
- Test in the browsers your network approves.

If Playwright and a browser are available offline in your environment, browser tests are welcome, but `check.py` and the manual checklist are the required minimum.

---

## 9. Build phases

Stop after each phase and summarize what changed, what's left, and any deviations from this spec.

| Phase | Deliverable | Done when |
|---|---|---|
| 1 | Skeleton: layout, design tokens, theme toggle, navigation, `serve.py`, `check.py`, landing page with placeholder cards, **`scene.js`, `scrolly.js`, and the `_style.html` design-language page** | `check.py` passes; every page loads offline; **design language approved** |
| 2 | **Vertical slice:** agent loop (section 6.2), complete with narrative, sandbox, reduced motion, and keyboard support | Section 6.2 acceptance met; **shown to 3 to 5 target developers**, with their feedback recorded before more sections are built |
| 2b | Harness anatomy | Section 6.1 acceptance criteria met |
| 3 | Context window simulator and token growth explorer | Section 6.3 and 6.4 acceptance criteria met |
| 4 | Extension chooser | Section 6.5 acceptance criteria met |
| 5 | Quiz component, all knowledge checks, review page, progress marking | Section 6.6 and 7 met |
| 6 | Polish: accessibility pass, responsive pass, README for instructors | Full manual checklist passes |
| 7a | Inside an extension: measured data and content (section 6.7) | Data reproduces from the course examples; `check.py` validates it |
| 7b | Inside an extension: page, lenses, cost ledger, knowledge check | Section 6.7 acceptance criteria met; full manual checklist passes |

Commit at the end of each phase with a message describing the phase. Keep each commit focused.

---

## 10. Working rules for the agent

- Ask before adding any dependency, file outside the layout in section 4, or feature outside section 3.
- Keep every file readable by an instructor: short functions, comments that explain *why*, no minified code.
- Keep instructor-facing notes out of student-facing pages (section 7).
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

Copy the course folder into the repo under `course/`, or give the agent access to it, before starting Phase 2. Phase 2 is blocked until it is available.

---

## 12. Changelog

**v2**
- Repositioned the site as a visually compelling explorable explanation (section 1).
- Added the shared visual world, token blocks, and `_style.html` (section 5.1).
- Split motion rules into UI feedback and explanatory animation (section 5).
- Added guided narrative, predict-then-reveal, and a signature moment to every section (section 6).
- Added `scene.js`, `scrolly.js`, `content/site.json`, and `sections/_style.html` to the layout (section 4).
- Defined compaction edge cases: oversized results and overhead larger than the window (section 6.3).
- Mapped the "use a CLI" result to existing mechanisms; plugin question applies after every result (section 6.5).
- `check.py`: allowlisted SVG namespace URIs, banned absolute URLs in JSON too, specified emoji ranges, added JS import checks (section 8).
- Phases: design-language approval gate, and the agent loop as a vertical slice with user feedback before the other sections (section 9).
- Desktop only: phone and tablet layouts dropped from scope (sections 5 and 8).

**v2.1**
- Added "Inside an extension" as section 6 of 7: four lenses (MCP, skill, subagent, plugin) on one session, plus a cost ledger (sections 3, 4, 6.7, 7, 9).
- Added `skill` and `subagent` content roles for that section (section 6.7).
