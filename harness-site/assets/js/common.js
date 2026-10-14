/*
  common.js: shared behaviour for every page.

  - Theme toggle (light / dark, remembered when storage is available)
  - Content loading from content/*.json
  - Progress (which sections' knowledge checks are finished)
  - Landing page cards and section page header content

  Storage is optional. Every localStorage access is wrapped so the site
  works in private windows and on locked-down machines.
*/

// Site root, resolved from this file's location (assets/js/common.js).
// Resolving against import.meta.url keeps paths working from any subpath.
const SITE_ROOT = new URL("../../", import.meta.url);

// Replaced with the release version at deploy time (tools/stamp.py) so a
// new release never reads content cached from an old one.
const ASSET_VERSION = "dev";

const THEME_KEY = "harness-theme";
const PROGRESS_KEY = "harness-progress";

/* Storage ----------------------------------------------------------------- */

function storageGet(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function storageSet(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage unavailable: the choice simply is not remembered.
  }
}

/* Theme ------------------------------------------------------------------- */

function currentTheme() {
  const chosen = document.documentElement.dataset.theme;
  if (chosen === "light" || chosen === "dark") return chosen;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function initThemeToggle() {
  const button = document.getElementById("theme-toggle");
  if (!button) return;

  // The button says what it will switch to, so its label is always accurate.
  const render = () => {
    const isDark = currentTheme() === "dark";
    button.textContent = isDark ? "Light theme" : "Dark theme";
    button.setAttribute("aria-pressed", String(isDark));
  };

  button.addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    storageSet(THEME_KEY, next);
    render();
  });

  render();
}

/* Content ------------------------------------------------------------------ */

/** Load content/<name>.json. Throws with a readable message on failure. */
export async function loadContent(name) {
  const url = new URL(`content/${name}.json`, SITE_ROOT);
  url.searchParams.set("v", ASSET_VERSION);
  let response;
  try {
    response = await fetch(url);
  } catch (error) {
    throw new Error(`Could not load ${name}.json (${error.message}).`);
  }
  if (!response.ok) {
    throw new Error(`Could not load ${name}.json (HTTP ${response.status}).`);
  }
  return response.json();
}

/** Content links are written relative to the site root; resolve them. */
export function resolveSiteLink(path) {
  return new URL(path, SITE_ROOT).href;
}

/**
 * Show a visible message when content fails to load. The most common cause
 * is opening the page from file://, where browsers block fetch.
 */
export function showLoadError(error) {
  const box = document.createElement("div");
  box.className = "load-error";
  box.setAttribute("role", "alert");

  const strong = document.createElement("strong");
  strong.textContent = "Content did not load. ";
  box.append(strong, error.message, " ");

  if (window.location.protocol === "file:") {
    box.append(
      "Pages opened directly from disk cannot load content. " +
        "Run python3 tools/serve.py and open the address it prints."
    );
  }

  const main = document.querySelector("main") || document.body;
  main.prepend(box);
}

/* Progress ------------------------------------------------------------------ */

export function getCompleted() {
  try {
    const parsed = JSON.parse(storageGet(PROGRESS_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function markCompleted(sectionId) {
  const done = new Set(getCompleted());
  done.add(sectionId);
  storageSet(PROGRESS_KEY, JSON.stringify([...done]));
}

/* Page setup ---------------------------------------------------------------- */

/** Run on every page: theme toggle and current-page marking in the nav. */
export function initPage() {
  initThemeToggle();

  const here = new URL(window.location.href);
  here.hash = "";
  here.search = "";
  for (const link of document.querySelectorAll(".site-nav a")) {
    if (link.href === here.href) link.setAttribute("aria-current", "page");
  }
}

/** Small "completed" marker: an SVG check plus text, never color alone. */
function completedMarker() {
  const span = document.createElement("span");
  span.className = "card-done";
  span.innerHTML =
    '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" focusable="false">' +
    '<path d="M2 7.5 5.5 11 12 3.5" fill="none" stroke="currentColor" stroke-width="2.2" ' +
    'stroke-linecap="round" stroke-linejoin="round"/></svg>';
  span.append("Completed");
  return span;
}

/** Landing page: fill copy and section cards from content/site.json. */
export async function initLanding() {
  let site;
  try {
    site = await loadContent("site");
  } catch (error) {
    showLoadError(error);
    return null;
  }

  document.querySelector("[data-content='title']").textContent = site.title;
  document.querySelector("[data-content='description']").textContent = site.description;

  const courseLink = document.querySelector("[data-content='course-link']");
  if (courseLink) courseLink.href = resolveSiteLink(site.written_course_link);

  const done = new Set(getCompleted());
  const list = document.querySelector("[data-content='cards']");
  list.replaceChildren();

  site.sections.forEach((section, index) => {
    const item = document.createElement("li");
    const card = document.createElement("article");
    card.className = "card";

    const meta = document.createElement("div");
    meta.className = "card-meta";
    meta.textContent = String(index + 1).padStart(2, "0");
    if (done.has(section.id)) meta.append(completedMarker());

    const heading = document.createElement("h3");
    const link = document.createElement("a");
    link.href = resolveSiteLink(section.page);
    link.textContent = section.title;
    heading.append(link);

    const summary = document.createElement("p");
    summary.textContent = section.summary;

    card.append(meta, heading, summary);
    item.append(card);
    list.append(item);
  });

  return site;
}

/**
 * Section pages: fill the concept line and the "Go deeper" link.
 * `pick` selects the part of the file holding concept and module_link;
 * the review page keeps its copy inside quizzes.json.
 */
export async function initSection(contentName, pick = (data) => data) {
  let data;
  try {
    data = await loadContent(contentName);
  } catch (error) {
    showLoadError(error);
    return null;
  }
  const content = pick(data);

  const concept = document.querySelector("[data-content='concept']");
  if (concept) concept.textContent = content.concept;

  const deeper = document.querySelector("[data-content='module-link']");
  if (deeper) deeper.href = resolveSiteLink(content.module_link);

  return data;
}
