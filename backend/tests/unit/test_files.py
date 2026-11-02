import hashlib

from solids.infrastructure.files import scan_obj_folder


def test_scan_lists_only_top_level_obj_with_sha256_and_size(tmp_path):
    (tmp_path / "wf_a_3pt.obj").write_bytes(b"v 0 0 0\n")
    (tmp_path / "UPPER.OBJ").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"ignored")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "nested.obj").write_bytes(b"ignored")

    entries = scan_obj_folder(tmp_path)

    assert [e.filename for e in entries] == ["UPPER.OBJ", "wf_a_3pt.obj"]
    by_name = {e.filename: e for e in entries}
    assert by_name["wf_a_3pt.obj"].key == "wf_a_3"
    assert by_name["wf_a_3pt.obj"].sha256 == hashlib.sha256(b"v 0 0 0\n").hexdigest()
    assert by_name["wf_a_3pt.obj"].size_bytes == 8


def test_scan_does_not_modify_files(tmp_path):
    f = tmp_path / "a.obj"
    f.write_bytes(b"data")
    before = (f.read_bytes(), f.stat().st_mtime_ns)
    scan_obj_folder(tmp_path)
    assert (f.read_bytes(), f.stat().st_mtime_ns) == before


def test_scan_hashes_in_blocks(tmp_path):
    f = tmp_path / "big.obj"
    f.write_bytes(b"a" * (3 * 1024 * 1024 + 5))
    (entry,) = scan_obj_folder(tmp_path, block_size=1024 * 1024)
    assert entry.sha256 == hashlib.sha256(b"a" * (3 * 1024 * 1024 + 5)).hexdigest()
