import os
import stat
import sys
from pathlib import Path


def test_backup_file_is_0600_under_umask_022(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    import database
    monkeypatch.setattr(database.subprocess, "run", lambda *a, **k: None)
    out = tmp_path / "b.dump"
    old = os.umask(0o022)
    try:
        monkeypatch.setattr(sys, "argv", ["database.py", "--context", "kind-test", "backup", "--output", str(out)])
        try:
            database.main()
        except SystemExit:
            pass
    finally:
        os.umask(old)
    assert stat.S_IMODE(out.stat().st_mode) == 0o600


def test_second_backup_to_same_file_fails_and_keeps_original(tmp_path, monkeypatch):
    import pytest

    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    import database

    runs = []
    monkeypatch.setattr(database.subprocess, "run", lambda *a, **k: runs.append(a))
    out = tmp_path / "b.dump"
    out.write_bytes(b"original backup")
    monkeypatch.setattr(sys, "argv", ["database.py", "--context", "kind-test", "backup", "--output", str(out)])
    with pytest.raises(FileExistsError):
        database.main()
    assert out.read_bytes() == b"original backup"
    assert runs == []
