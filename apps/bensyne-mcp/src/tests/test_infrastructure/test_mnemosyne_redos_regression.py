"""ReDoS regression test — mnemosyne-memory version-A fact-extractor regex.

Background
----------
mnemosyne-memory 3.14.0 ships a "version A" fact-extraction regex (in
``mnemosyne.core.beam.extract_and_store_facts``) that catastrophically backtracks
on long, whitespace-free, mixed-case letter runs that contain no trailing
``\\d+\\.\\d+`` (a version number). The real-world trigger is a **base64 blob**
(e.g. ``{"result":"<base64>"}``) that racochu reads and feeds straight into
``remember()`` -> ``extract_and_store_facts()``. The backtracking hangs the
event loop at ~98% CPU and silently drops chunks.

3.15.1 fixes the regex by changing the inner ``\\s*`` to ``\\s+``.

This test is the behavioral guard: it feeds the fact-extraction path a long
whitespace-free mixed-case run and asserts it completes within a bounded time.

IMPORTANT — why a subprocess?
The catastrophic backtracking holds the interpreter GIL for its whole (very
long) run, starving *every* other thread in the process — including any
in-process timeout thread. So an in-process ``threading`` guard cannot even
fire. The only reliable way to bound the hang is to run the extraction in a
separate process and kill it on timeout. That is what this test does: a hang
becomes a clean ``TimeoutExpired`` -> test failure, instead of freezing the
whole suite.

On 3.14.0 the child hangs and this test FAILS (red). On 3.15.1 the child
returns instantly and the test PASSES (green).
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

# 240-char whitespace-free mixed-case run (120 x "aB"), no digits, no "\\d+\\.\\d+".
# Long enough to trigger catastrophic backtracking on the vulnerable regex; short
# enough that the fixed regex handles it in microseconds.
REDO_S_TRIGGER = "aB" * 120

# Observed real-world killer shape: a base64-like envelope. base64 is drawn from
# [A-Za-z0-9+/] so it also contains the mixed-case runs the version-A regex chokes on.
REDO_S_BASE64_TRIGGER = "eyJ" + ("aB" * 119) + "=="  # realistic base64-ish, no version number

# Bounded wait. Comfortably above the 3.15.1 run time (ms) but far below the
# 3.14.0 hang time (8s+ and growing), so a regression fails cleanly instead of
# hanging the suite.
TIMEOUT_SECONDS = 10.0

# Script executed in the child process. Runs the *real* fact-extraction path
# (``extract_and_store_facts``) on the trigger, then reports how long it took.
# Kept as a plain string so the child imports mnemosyne fresh in its own process.
_CHILD_SCRIPT = textwrap.dedent(
    """
    import time
    import tempfile
    from mnemosyne.core.memory import Mnemosyne

    tmp = tempfile.mkdtemp()
    m = Mnemosyne(db_path=tmp + "/mnemo.db")
    start = time.time()
    m.beam.extract_and_store_facts({trigger!r})
    print(f"OK {{time.time() - start:.4f}}")
    """
)


def _run_extraction_in_subprocess(trigger: str) -> str:
    """Run extract_and_store_facts(trigger) in a child process, return its stdout.

    Raises subprocess.TimeoutExpired if the child does not finish within
    TIMEOUT_SECONDS (i.e. the regex is backtracking -> ReDoS regression).
    """
    script = _CHILD_SCRIPT.format(trigger=trigger)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
    )
    assert result.returncode == 0, f"child process crashed:\n{result.stderr}"
    return result.stdout


class TestMnemosyneRedosRegression:
    """Guards against the version-A regex ReDoS in mnemosyne-memory."""

    def test_long_mixed_case_run_completes_promptly(self) -> None:
        """A 240-char whitespace-free mixed-case run must not hang the extractor."""
        try:
            stdout = _run_extraction_in_subprocess(REDO_S_TRIGGER)
        except subprocess.TimeoutExpired:
            pytest.fail(
                f"ReDoS REGRESSION: extract_and_store_facts hung > {TIMEOUT_SECONDS}s on a "
                f"{len(REDO_S_TRIGGER)}-char whitespace-free mixed-case run. "
                "mnemosyne-memory is likely < 3.15.1 (vulnerable version-A regex)."
            )
        assert "OK" in stdout, f"child did not complete fact extraction:\n{stdout}"

    def test_base64_style_run_completes_promptly(self) -> None:
        """The observed base64-like killer shape must not hang the extractor either."""
        try:
            stdout = _run_extraction_in_subprocess(REDO_S_BASE64_TRIGGER)
        except subprocess.TimeoutExpired:
            pytest.fail(
                f"ReDoS REGRESSION: extract_and_store_facts hung > {TIMEOUT_SECONDS}s on a "
                f"{len(REDO_S_BASE64_TRIGGER)}-char base64-like run. "
                "mnemosyne-memory is likely < 3.15.1 (vulnerable version-A regex)."
            )
        assert "OK" in stdout, f"child did not complete fact extraction:\n{stdout}"
