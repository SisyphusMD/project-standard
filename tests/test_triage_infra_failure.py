"""The infra-vs-ours discriminator, tested at the standard because both projects vendor it.

The risk this guards is specific: a retry rule that is even slightly too generous becomes a way to
launder flaky tests into green builds, and nobody notices because the build is green. So the cases
that matter most here are the ones where it must REFUSE to retry.

    python3 -m pytest tests/test_triage_infra_failure.py
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
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


# --- a step of ours that the runner's resolver failed ------------------------------------------

_INSTALL = {"name": "Install the rendered formula and run it", "conclusion": "failure",
            "started_at": "2026-09-16T04:18:27Z", "completed_at": "2026-09-16T04:23:48Z"}
_PYTEST = {"name": "Pytest", "conclusion": "failure",
           "started_at": "2026-09-16T04:10:00Z", "completed_at": "2026-09-16T04:12:00Z"}
_SETUP = {"name": "Set up job", "conclusion": "success",
          "started_at": "2026-09-16T04:09:00Z", "completed_at": "2026-09-16T04:09:30Z"}

#: Trimmed from the observed job log (run 35055059591): the formula installed, then `brew test`
#: bootstrapped Homebrew's Ruby harness and the runner could not resolve rubygems.org.
_RESOLVER_LOG = """\
2026-09-16T04:22:10.5216400Z 🍺  /usr/local/Cellar/whiskerless/0.1.3: 656 files, 6.3MB
2026-09-16T04:22:32.4522250Z Fetching source index from https://rubygems.org/
2026-09-16T04:23:02.4802700Z Retrying fetcher due to error (2/4): Bundler::HTTPError Could not fetch specs from https://rubygems.org/ due to underlying error <Socket::ResolutionError: Failed to open TCP connection to rubygems.org:443 (getaddrinfo(3): nodename nor servname provided, or not known) (https://rubygems.org/specs.4.8.gz)>
2026-09-16T04:23:45.5104420Z Error: failed to run `.../bin/bundle install`!
2026-09-16T04:23:48.4071580Z ##[error]Process completed with exit code 1.
"""


def _logged_job(job_id: int, *steps: dict) -> dict:
    return {"id": job_id, "name": "Homebrew formula builds and runs (x86_64, floor)",
            "conclusion": "failure", "steps": list(steps)}


def test_a_resolver_failure_inside_our_own_step_is_retryable() -> None:
    """The observed case. `Set up job` was green, one of OUR steps failed — and the step-name rule
    alone refused it, leaving a DNS outage on the runner red until a human re-ran it."""
    infra, report = _load().triage([_logged_job(7, _SETUP, _INSTALL)], {7: _RESOLVER_LOG})
    assert infra is True
    assert any("retryable" in line and "nodename nor servname" in line for line in report)


def test_without_the_log_the_same_failure_is_ours() -> None:
    """A log that could not be fetched must fall on the safe side: not retrying."""
    infra, report = _load().triage([_logged_job(7, _SETUP, _INSTALL)], {})
    assert infra is False
    assert any("not retrying" in line for line in report)


def test_a_signature_printed_by_another_step_does_not_launder_ours() -> None:
    """The laundering risk, concretely: an earlier step in the same job legitimately prints a
    resolver error (a test of offline behaviour, say), and then a later step of ours fails for a
    real reason. Only the FAILED step's own timestamp window is read, so the earlier line is not
    evidence for it."""
    log = (
        "2026-09-16T04:09:10.0000000Z expected: Could not resolve host: example.invalid\n"
        "2026-09-16T04:11:00.0000000Z FAILED tests/test_x.py::test_y"
    )
    infra, _ = _load().triage([_logged_job(8, _SETUP, _PYTEST)], {8: log})
    assert infra is False


def test_a_real_failure_in_the_same_run_still_vetoes_the_retry() -> None:
    """`rerun-failed-jobs` is all-or-nothing, so the resolver failure in one job cannot carry a
    genuine failure in another."""
    module = _load()
    infra, _ = module.triage(
        [_logged_job(7, _SETUP, _INSTALL), {"id": 9, "name": "Test", "conclusion": "failure",
                                             "steps": [_SETUP, _PYTEST]}],
        {7: _RESOLVER_LOG, 9: "2026-09-16T04:11:00.0000000Z FAILED tests/test_x.py::test_y"},
    )
    assert infra is False


def test_a_line_in_a_boundary_second_belongs_to_neither_step() -> None:
    """Adjacent steps hand over within one second, and GitHub records step times without a
    fraction — so a line in that second could be either step's. A successful earlier step that
    prints a resolver error as it exits must not lend it to the step that then fails."""
    log = (
        "2026-09-16T04:18:27.1000000Z curl: (6) Could not resolve host: github.com\n"
        "2026-09-16T04:18:40.0000000Z FAILED tests/test_x.py::test_y\n"
        "2026-09-16T04:23:48.1000000Z Could not resolve host: github.com"
    )
    assert _load().transient_network_failure(log, _INSTALL) is None


def test_a_resolver_error_the_step_survived_does_not_excuse_a_later_failure() -> None:
    """Same step, two events: an expected DNS error early (a retried fetch, an offline-behaviour
    test) and a genuine failure pages later. Only the closing lines count."""
    module = _load()
    early = "2026-09-16T04:19:00.0000000Z Could not resolve host: pypi.org (expected, retried)"
    filler = [f"2026-09-16T04:20:{i:02d}.0000000Z line {i}" for i in range(module.TAIL_LINES)]
    late = "2026-09-16T04:21:00.0000000Z FAILED tests/test_x.py::test_y - AssertionError"
    assert module.transient_network_failure("\n".join([early, *filler, late]), _INSTALL) is None


def test_a_hostname_the_repository_broke_is_not_an_outage() -> None:
    """The exact curl spelling, for a host nobody legitimately reaches: a typo in a URL we own.
    Re-running it can only fail again, so it must stay red."""
    log = "2026-09-16T04:20:00.0000000Z curl: (6) Could not resolve host: typo.invalid"
    assert _load().transient_network_failure(log, _INSTALL) is None


def test_a_step_that_never_started_owns_no_log_lines() -> None:
    """A skipped-then-failed step has no timestamps, and must not inherit the whole log."""
    module = _load()
    assert module.transient_network_failure(_RESOLVER_LOG, {"name": "x", "conclusion": "failure"}) is None


@pytest.mark.parametrize("bad", ["Connection refused", "execution expired", "ReadTimeoutError"])
def test_timeouts_and_refusals_are_deliberately_not_signatures(bad: str) -> None:
    """A broker or fixture that failed to start produces exactly these, so they must stay ours."""
    module = _load()
    assert not any(bad in sig for sig in module.TRANSIENT_NETWORK_SIGNATURES)
    log = f"2026-09-16T04:20:00.0000000Z Error: {bad}"
    assert module.transient_network_failure(log, _INSTALL) is None


def test_the_cli_reads_a_logs_directory(tmp_path) -> None:
    """The end-to-end shape the workflow uses: jobs.json plus `<job id>.log` files."""
    (tmp_path / "jobs.json").write_text(json.dumps({"jobs": [_logged_job(7, _SETUP, _INSTALL)]}))
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "7.log").write_text(_RESOLVER_LOG)
    (logs / "not-a-job.log").write_text("ignored")
    out = subprocess.run([sys.executable, str(_SCRIPT), str(tmp_path / "jobs.json"), str(logs)],
                         capture_output=True, text=True, check=True).stdout
    assert out.startswith("infra=true\n")
    assert "retryable" in out
