# Inside the Harness: interactive companion site

A static, offline website that teaches harness concepts through explorable visuals. It accompanies the written "What Is a Harness?" course, which remains the source of truth for content. The full brief is in [`../docs/BUILD_SPEC.md`](../docs/BUILD_SPEC.md).

## Run it

Browsers block loading `content/*.json` from `file://` addresses, so open the site through a web server:

```bash
python3 tools/serve.py            # then open http://127.0.0.1:8000/
python3 tools/serve.py --port 9000
```

Any internal static web server works too. The site has no build step, no dependencies, and makes no network requests.

## Deploy

Copy this folder to any static host. All paths are relative, so it works from a subpath such as `/training/harness/`.

When you update a deployed copy, stamp it with a new version so browsers do not mix new pages with cached scripts:

```bash
cp -r harness-site /srv/training/harness
python3 harness-site/tools/stamp.py /srv/training/harness 2026-10-14
```

Run `stamp.py` on the deployed copy only, never on this folder. The GitHub Pages workflow does this automatically.

Links to the written course (`module_link`, `written_course_link`) are relative to the site root and default to a `course/` folder next to this one. Edit them in `content/` to match where the course is hosted.

## Edit content

All explanatory text lives in `content/`:

| File | Holds |
|---|---|
| `site.json` | Landing page title, description, section order, and card summaries |
| `anatomy.json`, `loop.json`, `context.json`, `tokens.json`, `extensions.json` | Each section's concept statement, "Go deeper" link, narrative steps, and simulation defaults |
| `quizzes.json` | Knowledge-check questions (3 to 4 per section, tagged by `section`), plus the review page's concept, link, and `question_ids` for its mixed set |

After editing, run the checks.

## Check

```bash
python3 tools/check.py
```

This validates the content JSON, links and asset paths, the absence of external URLs and emoji, and basic accessibility markup. It exits non-zero on failure. Warnings about missing `course/` links are expected until the written course is copied in.

Before each review, also run the manual checks in spec section 8: keyboard only, widths of 360, 768, and 1280px, light and dark themes, reduced motion, and networking disabled.

## Layout

```text
index.html            landing page
sections/             one page per section, plus _style.html (design language)
assets/css/site.css   design tokens and layout
assets/js/common.js   theme, content loading, progress
assets/js/scene.js    the shared visual world and token-block primitives
assets/js/scrolly.js  links narrative scroll steps to scene states
assets/js/quiz.js     knowledge checks; finishing one marks the section complete
content/              all editable text and defaults
tools/                serve.py and check.py (Python standard library only)
```

`sections/_style.html` is the reference for how the model, the harness, and each content role are drawn. Review visual changes there first.
