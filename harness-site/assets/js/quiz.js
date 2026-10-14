/*
  quiz.js: the shared knowledge check (spec section 6.6).

  Any element with data-quiz="<section id>" becomes a quiz:
    - a section id shows that section's questions from quizzes.json
    - "review" shows the mixed set listed in review.question_ids

  One question at a time. Picking a choice locks the question, states
  "Correct" or "Not quite" in text (color is only a second signal), shows
  the explanation, and offers the next question. Finishing the last
  question marks the section complete for the course map.
*/

import { loadContent, showLoadError, getCompleted, markCompleted } from "./common.js";

const LETTERS = "ABCDEFGH";

function make(tag, className, textContent) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (textContent !== undefined) node.textContent = textContent;
  return node;
}

/** Questions for one quiz, in the order they should be asked. */
export function pickQuestions(data, sectionId) {
  if (sectionId === "review") {
    const byId = new Map(data.questions.map((q) => [q.id, q]));
    return data.review.question_ids.map((id) => byId.get(id)).filter(Boolean);
  }
  return data.questions.filter((q) => q.section === sectionId);
}

/**
 * Render a quiz into `root`. `onFinish(score, total)` runs when the last
 * question has been answered.
 */
export function mountQuiz(root, questions, { onFinish = () => {}, wasCompleted = false } = {}) {
  let index = 0;
  let score = 0;

  const status = make("p", "quiz-status");
  const body = make("div", "quiz-body");
  root.replaceChildren(status, body);

  function renderQuestion() {
    const q = questions[index];
    const promptId = `${root.id || "quiz"}-prompt-${index}`;
    status.textContent = `Question ${index + 1} of ${questions.length}`;

    const prompt = make("p", "quiz-prompt", q.prompt);
    prompt.id = promptId;

    const group = make("div", "quiz-choices");
    group.setAttribute("role", "group");
    group.setAttribute("aria-labelledby", promptId);

    const feedback = make("div", "quiz-feedback");
    feedback.setAttribute("aria-live", "polite");

    const buttons = q.choices.map((choice, i) => {
      const button = make("button", "quiz-choice");
      button.type = "button";
      button.append(make("span", "quiz-letter", LETTERS[i]), make("span", "quiz-text", choice));
      button.addEventListener("click", () => answer(i));
      return button;
    });
    group.append(...buttons);
    body.replaceChildren(prompt, group, feedback);

    let answered = false;
    function answer(chosen) {
      if (answered) return;
      answered = true;
      const right = chosen === q.answer;
      if (right) score += 1;

      buttons.forEach((button, i) => {
        // aria-disabled keeps focus on the clicked button; disabled would drop it.
        button.setAttribute("aria-disabled", "true");
        if (i === q.answer) {
          button.classList.add("is-answer");
          button.append(make("span", "quiz-mark", "Correct answer"));
        }
        if (i === chosen) {
          button.setAttribute("aria-pressed", "true");
          if (!right) {
            button.classList.add("is-wrong");
            button.append(make("span", "quiz-mark", "Your answer"));
          }
        }
      });

      feedback.className = `quiz-feedback ${right ? "is-right" : "is-wrong"}`;
      const verdict = make("p", "quiz-verdict", right ? "Correct." : "Not quite.");
      const explanation = make("p", "quiz-explanation", q.explanation);
      const last = index === questions.length - 1;
      const next = make("button", "button button-primary", last ? "See results" : "Next question");
      next.type = "button";
      next.addEventListener("click", () => {
        index += 1;
        if (last) renderResults();
        else renderQuestion();
        // Move focus to the new content so keyboard users keep their place.
        root.querySelector(".quiz-prompt, .quiz-result")?.focus();
      });
      feedback.append(verdict, explanation, next);
      next.focus();
    }

    prompt.tabIndex = -1;
  }

  function renderResults() {
    status.textContent = "Finished";
    onFinish(score, questions.length);

    const result = make("p", "quiz-result", `You answered ${score} of ${questions.length} correctly.`);
    result.tabIndex = -1;
    result.setAttribute("aria-live", "polite");
    const saved = getCompleted().includes(root.dataset.quiz);
    const note = make(
      "p",
      "note",
      saved
        ? "This section is marked complete on the course map."
        : "Progress could not be saved in this browser, so the course map will not show it."
    );
    const again = make("button", "button", "Try again");
    again.type = "button";
    again.addEventListener("click", () => {
      index = 0;
      score = 0;
      renderQuestion();
      root.querySelector(".quiz-prompt")?.focus();
    });
    body.replaceChildren(result, note, again);
  }

  if (wasCompleted) {
    const done = make("p", "note", "You finished this check before. Take it again any time.");
    root.insertBefore(done, body);
  }
  renderQuestion();
}

/** Find every [data-quiz] element on the page and mount its quiz. */
export async function initQuizzes() {
  const roots = document.querySelectorAll("[data-quiz]");
  if (!roots.length) return;
  let data;
  try {
    data = await loadContent("quizzes");
  } catch (error) {
    showLoadError(error);
    return;
  }
  for (const root of roots) {
    const sectionId = root.dataset.quiz;
    const questions = pickQuestions(data, sectionId);
    if (!questions.length) continue;
    mountQuiz(root, questions, {
      wasCompleted: getCompleted().includes(sectionId),
      onFinish: () => markCompleted(sectionId),
    });
  }
}

initQuizzes();
