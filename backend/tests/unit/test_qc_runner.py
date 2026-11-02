import pytest

from solids.infrastructure.qc_runner import IsolatedAnalyzer

FAKES = "support.qc_fakes:analyze"
GOOD = "v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\nf 1 3 2\nf 1 2 4\nf 2 3 4\nf 1 4 3\n"


@pytest.fixture
def analyzer():
    a = IsolatedAnalyzer(FAKES, timeout=20.0)
    yield a
    a.close()


def test_analyzes_in_a_child_process_and_returns_plain_json(tmp_path, analyzer):
    (tmp_path / "a.obj").write_text(GOOD)
    result = analyzer.analyze(tmp_path / "a.obj")
    assert result["status"] in {"ok", "with_issues"}
    assert isinstance(result["volume_m3"], dict) and "validity" in result["volume_m3"]  # Metric already converted


def test_the_same_child_serves_several_files(tmp_path, analyzer):
    for n in range(3):
        (tmp_path / f"{n}.obj").write_text(GOOD)
    pids = set()
    for n in range(3):
        analyzer.analyze(tmp_path / f"{n}.obj")
        pids.add(analyzer.pid)
    assert len(pids) == 1


def test_a_hanging_file_is_cut_off_and_the_next_one_still_works(tmp_path):
    a = IsolatedAnalyzer(FAKES, timeout=2.0)
    try:
        (tmp_path / "hang.obj").write_text("#hang\n" + GOOD)
        (tmp_path / "ok.obj").write_text(GOOD)
        bad = a.analyze(tmp_path / "hang.obj")
        assert bad["status"] == "failed" and "timeout" in bad["error"]
        import json
        json.dumps(bad, allow_nan=False)  # a parent-side failure must be storable like any other result
        assert a.analyze(tmp_path / "ok.obj")["status"] in {"ok", "with_issues"}
    finally:
        a.close()


def test_a_crashing_file_is_reported_and_the_batch_continues(tmp_path, analyzer):
    (tmp_path / "crash.obj").write_text("#crash\n" + GOOD)
    (tmp_path / "ok.obj").write_text(GOOD)
    bad = analyzer.analyze(tmp_path / "crash.obj")
    assert bad["status"] == "failed" and "process" in bad["error"]
    assert analyzer.analyze(tmp_path / "ok.obj")["status"] in {"ok", "with_issues"}


def test_close_terminates_the_child(tmp_path):
    a = IsolatedAnalyzer(FAKES, timeout=20.0)
    (tmp_path / "a.obj").write_text(GOOD)
    a.analyze(tmp_path / "a.obj")
    a.close()
    assert a.pid is None


def test_the_worker_runs_numerical_libraries_with_one_thread(tmp_path):
    (tmp_path / "a.obj").write_text(GOOD)
    a = IsolatedAnalyzer("support.qc_fakes:threads", timeout=20.0)
    try:
        assert a.analyze(tmp_path / "a.obj")["threads"] == "1"
    finally:
        a.close()
