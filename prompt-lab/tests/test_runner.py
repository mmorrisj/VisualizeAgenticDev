"""The runner checks, labels, and stores runs; configuration loads and validates."""

import pytest

from promptlab.backends import BackendError
from promptlab.config import load_models
from promptlab.runner import run_matrix, run_one
from promptlab.store import Store


@pytest.fixture()
def store(tmp_path):
    return Store(f"sqlite:///{tmp_path / 'lab.db'}")


@pytest.fixture()
def models():
    return load_models()


def test_mock_models_show_the_scripted_pattern(store, models):
    old, new = models["mock-old"], models["mock-new"]
    assert run_one("data-question", "terse", old, store=store).score == 0.0
    assert run_one("data-question", "informed", old, store=store).score == 1.0
    assert run_one("data-question", "terse", new, store=store).score == 1.0


def test_run_records_everything(store, models):
    run = run_one("summarize", "informed", models["mock-new"], repeat=2, profile="test", store=store)
    saved = store.runs(id=run.id)[0]
    assert saved.status == "ok" and saved.label == "synthetic" and saved.repeat == 2 and saved.profile == "test"
    assert saved.tokens["synthetic"] is True and isinstance(saved.tokens["input"], int)
    assert saved.chars_sent == len(saved.prompt) and saved.chars_received == len(saved.output)
    assert saved.check_details["details"]["facts_missing"] == []


def test_backend_failure_is_stored_not_dropped(store, models):
    class Failing:
        def complete(self, request, model):
            raise BackendError("gateway down")

    run = run_one("refactor", "terse", models["mock-old"], store=store, backend=Failing())
    saved = store.runs(id=run.id)[0]
    assert saved.status == "error" and saved.score is None and "gateway down" in saved.error
    assert saved.tokens["input"] == "not reported"


def test_matrix_covers_every_combination(store, models):
    runs = run_matrix(["data-question", "write-tests"], ["terse", "full"],
                      [models["mock-old"], models["mock-new"]], repeats=2, store=store)
    assert len(runs) == 2 * 2 * 2 * 2 == len(store.runs())


def test_prompt_is_the_only_difference_between_variants():
    from promptlab.tasks import load_task
    task = load_task("refactor")
    terse, full = task.build_user_message("terse"), task.build_user_message("full")
    assert terse.split("\n\n", 1)[1] == full.split(task.prompt("full"), 1)[1].lstrip("\n")


def test_models_file_is_valid_and_flags_unconfirmed():
    models = load_models()
    real = [m for m in models.values() if m.api != "mock"]
    assert len(real) == 8
    assert all(not m.confirmed for m in real)
    assert {m.family for m in real} == {"llama", "openai", "anthropic"}


def test_duplicate_model_ids_rejected(tmp_path):
    path = tmp_path / "models.yaml"
    entry = "  - {id: a, display: A, gateway_id: a, family: f, generation: 1, api: mock}\n"
    path.write_text("models:\n" + entry + entry)
    with pytest.raises(ValueError, match="duplicate"):
        load_models(path)
