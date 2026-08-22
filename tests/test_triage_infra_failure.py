"""The infra-vs-ours discriminator, tested at the standard because both projects vendor it.

The risk this guards is specific: a retry rule that is even slightly too generous becomes a way to
launder flaky tests into green builds, and nobody notices because the build is green. So the cases
that matter most here are the ones where it must REFUSE to retry.

    python3 -m pytest tests/test_triage_infra_failure.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "shared" / "packaging" / "triage-infra-failure.py"


def _load():
    spec = importlib.util.spec_from_file_location("triage", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _job(name: str, conclusion: str, **steps: str) -> dict:
    return {
        "name": name,
        "conclusion": conclusion,
        "steps": [{"name": n.replace("_", " "), "conclusion": c} for n, c in steps.items()],
    }


def test_a_runner_that_died_before_our_steps_is_infrastructural() -> None:
    """The observed case: `Set up job` was the only step, so none of ours ever ran."""
    infra, report = _load().triage([_job("Test (arm64)", "failure", Set_up_job="failure")])
    assert infra is True
    assert "Test (arm64)" in report[0]


def test_our_own_failing_step_is_never_retried() -> None:
    """The whole point. `Set up job` green above a failed step of ours means the runner did its
    part and the code did not."""
    infra, report = _load().triage(
        [_job("Test", "failure", Set_up_job="success", Pytest="failure")]
    )
    assert infra is False
    assert any("not retrying" in line for line in report)


def test_one_real_failure_among_infra_failures_still_refuses() -> None:
    """A retry is all-or-nothing — `rerun-failed-jobs` re-runs every failed job in the run — so a
    single genuine failure anywhere in it must veto the whole retry. Judging each job on its own
    would re-run the real failure too and call the result transient."""
    module = _load()
    infra, _ = module.triage([
        _job("A", "failure", Set_up_job="failure"),
        _job("B", "failure", Set_up_job="success", Pytest="failure"),
    ])
    assert infra is False


def test_nothing_failed_is_not_something_to_retry() -> None:
    infra, report = _load().triage([_job("A", "success", Set_up_job="success")])
    assert infra is False
    assert report == []


def test_a_failed_job_with_no_steps_recorded_counts_as_infrastructural() -> None:
    """A job that failed so early GitHub recorded no steps at all cannot have been our code —
    there was nothing of ours to run."""
    infra, report = _load().triage([_job("A", "failure")])
    assert infra is True
    assert "(none recorded)" in report[0]


@pytest.mark.parametrize("phase", ["Set up job", "Set up runner"])
def test_both_runner_phases_count(phase: str) -> None:
    module = _load()
    infra, _ = module.triage([{"name": "A", "conclusion": "failure",
                               "steps": [{"name": phase, "conclusion": "failure"}]}])
    assert infra is True


def test_complete_job_is_deliberately_not_a_runner_phase() -> None:
    """It fails AFTER our steps have uploaded artifacts, and artifacts are immutable within a run —
    so a re-run fails on the duplicate name rather than repairing anything. A `Complete job`
    failure also means the work itself finished."""
    module = _load()
    assert "Complete job" not in module.RUNNER_PHASES
    infra, _ = module.triage([{"name": "A", "conclusion": "failure",
                               "steps": [{"name": "Complete job", "conclusion": "failure"}]}])
    assert infra is False
