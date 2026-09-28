from pathlib import Path

import filesystem_mcp_server as server


def test_list_files():
    result = server.list_files()
    assert result["count"] >= 4


def test_read_file():
    result = server.read_file("alice_singh.txt")
    assert "React" in result["content"]


def test_path_traversal_blocked():
    try:
        server.read_file("../requirements.txt")
    except ValueError as exc:
        assert "outside" in str(exc)
    else:
        raise AssertionError("Traversal was not blocked")


def test_batch_process():
    result = server.batch_process(["alice_singh.txt", "rahul_mehta.txt"])
    assert result["processed"] == 2
    assert result["errors"] == []
