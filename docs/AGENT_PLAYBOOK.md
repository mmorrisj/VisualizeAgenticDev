# Agent playbook: building explorable lessons

This document is for a coding agent asked to add a lesson to this site, or to build a site like it for another course. It records the approach used to build "Inside the Harness" (`harness-site/`) from the "What Is a Harness?" course (`course/`), including what the course owner asked for, what they rejected, and the mistakes that were caught along the way.

Read it in full before writing anything. Then read [`BUILD_SPEC.md`](BUILD_SPEC.md), which is the contract, and [`../harness-site/README.md`](../harness-site/README.md), which explains how the site runs, deploys, and is checked.

---

## 1. What you are building

An **explorable explanation**: a page where a student watches a real mechanism work, then operates it themselves. It sits next to a written course and does not replace it.

The course owner's direction, in order of how strongly it was stated:

1. **Visually compelling, not a game.** An early "borderline video game" idea was explicitly dropped: "let's not force the game." No points, levels, avatars, or win states. Knowledge checks are self-checks.
2. **Explain real functionality, not analogies.** A narrative that ended each step with a "take away" moral was rejected. Each step says what the software actually does: which bytes go where, which component decides, what the number is.
3. **Show the mechanism moving.** The owner asked for an anatomy walkthrough where "the user hits play and you see an interactive line travel through the workflow as the text explains each component." That pattern (Play, a visible path, synchronized explanation) is the house style.
4. **Generic and concrete, together.** When a worked example ("fix a bug": grep, read, edit, test) replaced the generic walkthrough, the owner asked for both back. The anatomy page now has two tabs: "How it works" and "Example: fix a bug." Default to keeping the general explanation and adding the concrete case beside it.
5. **Desktop only.** "No one will utilize the class on a phone; maximize optimizations for desktop." Test at 1280, 1440, and 1920px. Do not spend effort on narrow layouts.
6. **Instructor material is never prominent.** Instructor notes, build notes, source notes, and the design-language page stay in the README, the repository, or a quiet footnote. Course files named `*INSTRUCTOR*` are not published.

## 2. Hard constraints

These are enforced by `harness-site/tools/check.py` or by the deploy workflow. Breaking one fails CI.

- **Static site.** No build step, no runtime dependencies, no package manager, no CDN. Plain HTML, CSS, and ES modules.
- **Offline.** No `http://` or `https://` anywhere in HTML, CSS, JS, or JSON, except the SVG/XLink/XHTML namespace URIs. Links to the written course are relative.
- **Works from a subpath.** Resolve paths against `import.meta.url` (see `SITE_ROOT` in `common.js`), never against `/`.
- **Content lives in `content/*.json`.** All explanatory text, numbers, and defaults. JavaScript draws and wires; it does not hold prose.
- **No emoji or pictographs, and never the word "beginner."**
- **Accessibility markup.** Every `<img>` has `alt`; every inline SVG has `role="img"` and a name, or is decorative; every button has a text label.
- **`localStorage` is optional.** Wrap every access in try/catch; the site must work when storage throws.
- **Python standard library only** for tools.

## 3. The working loop with the course owner

The owner prefers small, incremental changes, industry best practice, and honest feedback. The pattern that worked:

1. **One phase or one section per pull request,** opened as a draft. Each PR describes what changed, how it was tested, and any deviation from the spec.
2. **Stop after each PR** and summarize: what changed, what is left, decisions they need to make. Do not start the next phase until they say so. ("merge it, then start phase 5" is the typical go-ahead.)
3. **Ask only when the decision is theirs**: content direction, scope, anything that changes what students see. Otherwise pick the conventional option, say which you picked, and proceed.
4. **Report problems in the course material; do not silently fix them.** Two were found by measuring (see section 5). The site shows the measured value and the README notes the discrepancy.
5. **Be candid about weaknesses in your own work.** For example: the first quiz draft had the correct answer as the longest choice in 21 of 22 questions. That was reported, then fixed, and a check was added so it cannot recur.

## 4. Anatomy of a section page

Every section follows the same order. Copy an existing page (`sections/loop.html` is the simplest) rather than starting from scratch.

| Part | Purpose | Notes |
|---|---|---|
| Concept line | One sentence stating the mechanism | From `content/<section>.json` → `concept` |
| **Signature moment** | The one visual a student should remember | Decide it before building anything. Write it in the spec. |
| Guided narrative | The mechanism explained step by step, with the scene in sync | Either scroll-linked steps (`scrolly.js`) or a Play tour with Back/Next (anatomy) |
| Predict (optional) | Ask before revealing | Unscored; reveal explains the answer |
| Sandbox | The student operates the mechanism | Stepper, simulator, or chooser. Side panel explains the current state in an `aria-live` region |
| Knowledge check | 3 to 4 questions | `quiz.js`, driven by `content/quizzes.json` |
| Go deeper | Link to the written module | Relative link from `module_link` |
| Source note | Where the numbers came from | Quiet, small text; never a banner |

Examples of signature moments that worked:

- **Agent loop:** every turn, the whole conversation travels back into the model as a growing train of blocks.
- **Anatomy:** a line travels through the harness parts as the text explains each one; "Show model only" removes the harness and leaves the model emitting text into nothing.
- **Context window:** the window fills, crosses the compaction threshold, and the file contents visibly crumble into a hatched summary.
- **Token growth:** focused and broad sessions side by side; the broad session's total-paid pile towers over the focused one while their final context sizes look almost the same.

## 5. Data: measure, don't invent

The most important rule. Every number a student sees either comes from running the course's own code, or is labelled illustrative on the page.

**How the harness numbers were produced.** The course ships `course/mini-harness/`, a teaching harness with a scripted mock backend (`--backend mock --scenario scenarios/<name>.json`). It estimates tokens as `len(json.dumps(obj)) // 4` (`backends.py: estimate_tokens`). A scratch script drove the harness through a scenario, recorded each request's parts (system prompt, tool definitions, instructions, conversation, tool results) using the same estimator on the same JSON serialization, and wrote the values into `content/*.json`.

Rules that came out of it:

- **Measure with the course's own estimator and serialization,** so a student who runs the lab gets the same numbers.
- **Make the parts add up.** The first measurement's parts did not sum to the request total, because the JSON wrapper around messages has its own size. That remainder was assigned to the conversation part, and `check.py` now verifies that the parts sum to each total. Add the same kind of check for any new data.
- **Keep measurement scripts outside the site** (a scratch directory, or a `tools/measure_*.py` if the owner wants them versioned). The site ships data, not the scripts that made it.
- **When the course disagrees with the measurement, show the measurement and tell the owner.** Found so far: negative `cache_write` values in Module 7's `sample-cached-session.jsonl`, and Module 1's README printing about 655 and 744 tokens where the harness produces 696 and 785.
- **Label anything not measured.** The context simulator uses a small badge: "Illustrative numbers."

## 6. Visual language

`sections/_style.html` is the reference, and `assets/js/scene.js` holds the primitives. Reuse them; do not draw a second version of the model or the harness.

- **One shared world.** The model is a sealed box with no connections of its own. Six harness parts surround it (Instructions, Tools, Context, Permissions, Memory, Interface). "You" sits outside on one side; "Your files, shell, APIs" on the other. New sections should zoom into this world, not invent another.
- **Content roles have fixed colors and order:** system, tools, instructions, user, model, result, summary (`ROLES` in `scene.js`). A compaction summary is hatched, never just a color.
- **Token blocks.** One block stands for a fixed number of tokens, stated on the page ("One block = 10 tokens" on the agent loop page).
- **Colors come from CSS custom properties** defined for light and dark themes in `site.css`. Never hard-code a color in JS.
- **Color is never the only signal.** Pair it with text, a pattern, a dashed outline, or a label.
- **Motion explains, then gets out of the way.** UI feedback under 300ms. With `prefers-reduced-motion: reduce`, every animation jumps to its end state; never show a blank or half-drawn scene.

Useful primitives: `createScene`, `setSceneLabel`, `setSceneInteractive`, `drawWorld` / `mountWorld`, `drawModel`, `drawComponent`, `drawBlocks`, `drawWindow`, `drawSegment`, `drawArrow`, `renderLegend`, `animate`, `prefersReducedMotion`. Scroll-linked narratives use `createScrolly({ steps, onStep, prev, next, status })`, where `onStep(index)` must rebuild the scene from the index alone so Back restores a state exactly.

## 7. Writing the copy

- **Say what happens, concretely.** "The harness appends the tool result to the conversation and sends all 963 tokens again" beats "the model remembers what it saw."
- **Use the real names**: `read_file`, `tool_use`, the actual file path, the actual request number.
- **No morals, no "the takeaway is."** The mechanism is the point.
- **Plain sentences.** One idea per step. Narrative steps are short; detail goes in the sandbox panel.
- **Keyboard hints are visible** under each interactive area (`Keys: Left Right step`).

## 8. Knowledge checks

- **Source:** each course module's "Check your understanding" section. Those are free-response, so you write the wrong choices.
- **3 to 4 questions per section**, conceptual, not trivia about the page.
- **Wrong choices are specific, plausible misconceptions** ("Prompt caching is working, so repeated content is no longer counted"), not jokes.
- **Balance length.** The correct choice must not reliably be the longest. Keep correct choices short and move the detail into the explanation. `check.py` fails if the correct choice is longest in more than half the questions.
- **Every question has an explanation** that teaches, shown after any answer.
- **Feedback is text first:** "Correct." / "Not quite." The correct answer and the student's pick are labelled in words.
- **The review page** draws a mixed set by id (`review.question_ids`) and must cover every section.
- **Completion** means the section's check was finished, not passed. It marks the course-map card "Completed."

## 9. Adding a section: file checklist

1. Spec first: add a subsection to `BUILD_SPEC.md` section 6 with concept, signature moment, interactions, content shape, and acceptance criteria. Get it approved.
2. Measure the data (section 5).
3. `content/<section>.json`: concept, `module_link`, narrative steps, data, `source_note`.
4. `sections/<section>.html`: copy an existing page. **The nav is duplicated in every HTML page**; add the new link to all of them, and update every "Section N of M" badge.
5. `assets/js/<section>.js`: one module; import from `common.js` and `scene.js`; call `initPage()` and `initSection("<section>")`.
6. `content/site.json`: add the section card in recommended order.
7. `content/quizzes.json`: 3 to 4 questions tagged with the section id; add one to `review.question_ids`.
8. `tools/check.py`: add the file to `CONTENT_SCHEMAS` and write a `check_<section>()` validator for its data (ids unique, references resolve, numbers add up).
9. Styles in `assets/css/site.css`, using existing tokens.
10. Update `harness-site/README.md` (the course-map table and layout list).

## 10. Quality gates before every PR

Run all of these. Paste the results into the PR description.

1. `python3 harness-site/tools/check.py` passes with no errors.
2. **Test a stamped, staged copy, not the source tree.** Copy the site, run `python3 tools/stamp.py <copy> <tag>`, delete `<copy>/tools`, and serve it next to a copy of `course/`. This is what students get.
3. **Every page at 1280, 1440, and 1920px, in light and dark themes:** no console errors, no horizontal scroll, no request leaving the local server.
4. **Keyboard only:** Tab through every page. Every stop has a visible focus indicator; nothing traps focus; every control works with Enter or Space; arrow keys step where the page says they do.
5. **Reduced motion:** with the OS setting on, step through every narrative and Play control; the scene is complete immediately after each action.
6. **Automated accessibility audit** (axe-core or equivalent), on every page, in both themes, after interacting. Zero violations is the bar.
7. **Networking disabled:** nothing missing.
8. **Read your own diff** as a reviewer would, before pushing.

If Playwright is available, script items 3 to 6; it catches regressions the manual pass misses. If it is not, do them by hand. The spec treats `check.py` and the manual checklist as the minimum.

## 11. Mistakes already made (do not repeat them)

| Symptom | Cause | Fix now in place |
|---|---|---|
| After a release, the anatomy narrative stopped advancing | Browser paired a new page with a cached old module | `tools/stamp.py` adds `?v=<version>` to every asset URL at deploy, plus `ASSET_VERSION` for content fetches |
| Space on a focused diagram part selected it **and** toggled Play | Two handlers for one key | Section handler ignores events with `defaultPrevented` |
| A `hidden` legend still showed | `display` rule overrode the attribute | Global `[hidden] { display: none !important; }` |
| Screen readers could not reach clickable diagram parts | Interactive children inside `svg role="img"` are hidden from assistive tech | `setSceneInteractive(svg)` sets `role="group"` on any scene with operable parts |
| Nested landmark warnings | Side panels were `<aside>` inside sections | Panels are plain `div`s |
| Dimmed narrative steps failed contrast (3.9:1) | Opacity 0.55 | Opacity 0.7 (passes 4.5:1) |
| Quiz answer guessable from length | Correct choices carried all the detail | Rebalanced; `check.py` guard |
| Request parts did not sum to the total | JSON wrapper overhead not assigned | Remainder assigned to conversation; sums validated |
| Course link URLs failed the no-URL check | SVG namespace URI | Namespace URIs allowlisted in `check.py` |
| A test reported "no focus ring" on SVG parts | Read computed style mid-transition | Wait for the transition before measuring |

## 12. Applying this to the `practical_exercises/agentic_development` curriculum

That course (modules 00 to 10) suits the approach well: its modules are built around failures that are set up to happen in front of the student, and each ships an artifact you can replay (test suites, linters, answer keys, `verify.sh`).

**Decide first, with the owner: preview or debrief?** The course is "rigged so the agent fails in front of you." A visual that shows the outcome first spoils that moment, and Module 07's would publish its answer key (`tools/answer_key.json`). The recommendation is to build these as debriefs: linked or unlocked after the exercise, or built on parallel examples rather than the graded ones.

Ranked candidates (an assessment, not a commitment):

1. **Module 03, air-gapped context engineering** (the course's spine). The same `collector.py` written without and with the vendored gauge docs, side by side, each of the six convention violations tagged with its failure shape. Sandbox: choose what goes into the context window (nothing, `gauge-1.x`, both versions, a version pin in `CLAUDE.md`) and see which output results and how many checks pass. Score both versions with the module's real tests.
2. **Module 07, reviewing AI-written code.** The real `base/` to `pr/` diff. Signature moment: "deletions are invisible", toggling between reading the new file (the removed guard is simply absent) and reading the diff (where it appears in red).
3. **Module 09, the hook over-blocking trap.** Each case in `tools/hook_cases.json` (15 cases) passes through the naive and the tokenizing hook; `git commit -m "document pip install steps"` gets blocked by the naive one.
4. **Module 04, spec-first.** A rate-limiter simulation with the ticket's three open decisions as toggles (per-key or global, refuse or admit, fixed or sliding window); a shared budget takes out every collector, not just the misconfigured one.
5. **Module 01, prompt vs. spec.** Type inputs into `parse_duration`; results sort into "fails loudly" and "silently wrong" (`"1.5h"` returns 18000).

Weaker fits: Module 05 (a scope-creep file view and a recovery decision flow, not a git simulator), Module 08 (a job timeline contrasting hang-forever failures with fail-fast ones), Module 02 (fold `CLAUDE.md` layering into the Module 03 piece). Modules 00, 06, and 10 are about doing the work end to end; leave them as written exercises.

Overlap: the existing site's anatomy, loop, context, and extensions sections already cover that course's Module 01 "what the model sees," the cost side of Module 02, and Module 09's comparison of mechanisms. Link to them instead of rebuilding.

Known issue in that course: Module 09's README says both "fifteen-case test suite" and "fails 7 of the 16 cases"; `hook_cases.json` has 15.

## 13. Definition of done for a section

- [ ] Spec subsection approved before building.
- [ ] Every number measured from course code, or labelled illustrative; sums validated in `check.py`.
- [ ] Signature moment works and is the first thing the narrative builds toward.
- [ ] Narrative explains functionality step by step; no analogies or morals.
- [ ] Sandbox lets the student operate the mechanism; panel explains each state in an `aria-live` region.
- [ ] 3 to 4 knowledge-check questions with balanced choices and teaching explanations; one added to the review set.
- [ ] Nav, badges, `site.json`, README, and `check.py` updated.
- [ ] All quality gates in section 10 pass on a stamped copy.
- [ ] No instructor-facing material visible to students.
- [ ] Draft PR opened with a summary, test results, deviations, and open questions; work stops for review.
