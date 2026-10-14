# Inside the Harness: interactive companion site

A static, offline website that teaches harness concepts through explorable visuals. It accompanies the written "What Is a Harness?" course, which remains the source of truth for content. The full brief is in [`../docs/BUILD_SPEC.md`](../docs/BUILD_SPEC.md).

This README is for instructors and maintainers. Students never see it; nothing instructor-facing is shown on the site itself.

## Run it

Browsers block loading `content/*.json` from `file://` addresses, so open the site through a web server:

```bash
python3 tools/serve.py            # then open http://127.0.0.1:8000/
python3 tools/serve.py --port 9000
```

Any internal static web server works too. The site has no build step, no dependencies, and makes no network requests. It is built for desktop browsers (tested at 1280, 1440, and 1920px wide).

## Teaching with it

### Map to the written course

| Site section | What students see | Pairs with |
|---|---|---|
| 1. Harness anatomy | The six harness parts around the model. "How it works" traces one request through them; "Example: fix a bug" replays a recorded edit, payload by payload. "Show model only" removes the harness. | Course README, sections 2 to 4 |
| 2. The agent loop | A recorded session: every request re-sends the whole conversation, drawn as a growing train of blocks. | Module 1, Build a harness |
| 3. The context window | Lab B replayed with compactions, Lab A's three runs compared, and a simulator for window size, overhead, and tool-result size. | Module 3, Context engineering |
| 4. Token growth | Focused and broad sessions side by side: final context versus total input paid, plus prompt caching. | Module 7, Token observability |
| 5. Choosing an extension | A decision flow, a comparison grid of seven mechanisms, and practice scenarios. | Module 5, Extensibility |
| 6. Final review | A mixed knowledge check across all sections. | Course README, section 12 |

Each section ends with a short knowledge check adapted from the matching module's "Check your understanding". Use the site after students read a module, or project it while you teach the module and let students explore afterwards.

### Suggested use in class

- **Demo, then explore.** Play the guided walkthrough on a projector, then give students time in the sandbox below it. Walkthroughs step with the keyboard, so you can stop on any frame to discuss it.
- **Use the prediction prompt.** The agent loop asks students to predict before revealing. Ask the room first, then reveal.
- **Knowledge checks are self-checks.** They are not graded and nothing is sent anywhere. A finished check marks its card "Completed" on the course map, stored only in that browser (`localStorage` key `harness-progress`). Clearing site data resets it. On machines that block storage, the site works normally and simply does not remember progress.
- **Rough timing, not yet validated with a class:** 10 to 15 minutes per section, 5 minutes for the review.

### Keyboard

| Where | Keys |
|---|---|
| Harness anatomy walkthrough | <kbd>Space</kbd> play or pause, <kbd>Left</kbd> <kbd>Right</kbd> step |
| Agent loop, context replay, simulator | <kbd>Left</kbd> <kbd>Right</kbd> step |
| Diagram parts and tabs | <kbd>Tab</kbd> to reach, <kbd>Enter</kbd> or <kbd>Space</kbd> to select, <kbd>Left</kbd> <kbd>Right</kbd> between tabs |

### Where the numbers come from

Token counts are measured by running the course's `mini-harness` with its mock backend, so they reproduce exactly. The "Inside an extension" data comes from `tools/measure_inside_extensions.py`, which runs the Module 5 examples against a fresh practice-app copy; re-run it after changing those examples, then run `check.py`. The harness estimates tokens as about 4 characters per token, the same convention the course uses. Anything not measured is labelled illustrative on the page.

Two discrepancies in the course material, found while measuring, are worth knowing if a student compares numbers:

- `sample-cached-session.jsonl` (Module 7) contains negative `cache_write` values (-65 and -275). The site derives fresh tokens as total minus cached instead of using that field.
- Module 1's README prints about 655 and 744 tokens for requests 3 and 4; running the harness gives 696 and 785. The site shows the measured values.

## Edit content

All explanatory text lives in `content/`:

| File | Holds |
|---|---|
| `site.json` | Landing page title, description, section order, and card summaries |
| `anatomy.json`, `loop.json`, `context.json`, `tokens.json`, `extensions.json` | Each section's concept statement, "Go deeper" link, narrative steps, and simulation defaults |
| `quizzes.json` | Knowledge-check questions (3 to 4 per section, tagged by `section`), plus the review page's concept, link, and `question_ids` for its mixed set |

To change a question, edit its `prompt`, `choices`, `answer` (zero-based index of the correct choice), and `explanation`. Keep wrong choices about as long and specific as the right one, so the answer cannot be guessed from its length. After any edit, run the checks.

## Check

```bash
python3 tools/check.py
```

This validates the content JSON (including question counts, answer indexes, and that the review covers every section), links and asset paths, the absence of external URLs and emoji, and basic accessibility markup. It exits non-zero on failure, and runs on every pull request.

Before publishing changes, also run the manual checks in spec section 8:

- Every section using only the keyboard; focus must always be visible.
- Widths of 1280, 1440, and 1920px.
- Light and dark themes, and the operating system's reduced-motion setting (animations must jump to their end state).
- Networking disabled: nothing may be missing.

## Deploy

Copy this folder to any static host. All paths are relative, so it works from a subpath such as `/training/harness/`.

When you update a deployed copy, stamp it with a new version so browsers do not mix new pages with cached scripts:

```bash
cp -r harness-site /srv/training/harness
python3 harness-site/tools/stamp.py /srv/training/harness 2026-10-14
```

Run `stamp.py` on the deployed copy only, never on this folder. The GitHub Pages workflow does this automatically, and also leaves out `tools/` and any course file named `*INSTRUCTOR*`.

Links to the written course (`module_link`, `written_course_link`) are relative to the site root and default to a `course/` folder next to this one. Edit them in `content/` to match where the course is hosted.

## Layout

```text
index.html             landing page
sections/              one page per section, plus _style.html (design language)
assets/css/site.css    design tokens and layout
assets/js/common.js    theme, content loading, progress
assets/js/scene.js     the shared visual world and token-block primitives
assets/js/scrolly.js   links narrative scroll steps to scene states
assets/js/quiz.js      knowledge checks; finishing one marks the section complete
assets/js/<section>.js one module per section page
content/               all editable text and defaults
tools/                 serve.py, check.py, stamp.py, measure_inside_extensions.py (Python standard library only)
```

`sections/_style.html` is the reference for how the model, the harness, and each content role are drawn. Review visual changes there first. It is not linked from the student pages.
