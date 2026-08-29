"""Runs the JavaScript smoke checks in tests/js/ and reports each as a test.

The rest of this suite exercises Flask routes and the data layer; none of it
loads the JavaScript those routes serve. That blind spot is not theoretical --
a refactor of job_fields.js once shipped a `stop(e)` that called itself, and
every Python test stayed green while the first click in the table exhausted
the stack.

The checks themselves live in tests/js/job_fields_checks.js, which runs the
real src/static/job_fields.js against a small DOM stub. This module only
shells out to node and turns each reported check into a test, so a failure
names the check rather than dumping a node traceback.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

CHECKS = Path(__file__).parent / "js" / "job_fields_checks.js"
NODE = shutil.which("node")


def _run_checks():
    proc = subprocess.run(
        [NODE, str(CHECKS)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise AssertionError(
            "the check runner itself failed to complete:\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    results = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    if not results:
        raise AssertionError(f"the check runner reported nothing:\n{proc.stderr}")
    return results


# Collected once at import so each check becomes its own test id. A failure
# here -- node missing, the file not parsing -- fails collection loudly rather
# than quietly reporting zero checks.
if NODE:
    _RESULTS = _run_checks()
else:  # pragma: no cover - exercised only where node is absent
    _RESULTS = []


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.parametrize(
    "result",
    _RESULTS,
    ids=[r["name"] for r in _RESULTS],
)
def test_job_fields_js(result):
    assert result["ok"], result["error"]


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_every_check_ran():
    """Guards against a runner that exits early and reports a green subset."""
    names = {r["name"] for r in _RESULTS}
    assert "module loads and exports its public surface" in names
    # Both views are exercised; a runner that dropped one would still look green.
    assert any(n.startswith("table: ") for n in names)
    assert any(n.startswith("modal: ") for n in names)
    assert len(_RESULTS) >= 20
