"""Faz kapıları (saf fonksiyonlar) testleri: contract hash, kapsam, placeholder."""

from gates import content_hash, out_of_scope_files, pattern_to_regex, scan_placeholders


def test_content_hash_is_order_independent_and_sensitive():
    assert content_hash({"a": 1, "b": [2, 3]}) == content_hash({"b": [2, 3], "a": 1})
    assert content_hash({"a": 1}) != content_hash({"a": 2})


def test_pattern_to_regex_ignores_meaningless():
    assert pattern_to_regex("") is None
    assert pattern_to_regex("  ") is None
    assert pattern_to_regex("<dosya>") is None
    assert pattern_to_regex("yok") is None
    assert pattern_to_regex("./app/*") is not None


def test_scope_matching():
    assert out_of_scope_files(["app/main.py"], ["app/*"]) == []
    assert out_of_scope_files(["app/sub/deep.py"], ["app/*"]) == []
    assert out_of_scope_files(["app/main.py"], ["app/"]) == []
    assert out_of_scope_files(["evil.py"], ["app/*"]) == ["evil.py"]
    # Boş/anlamsız desen → denetim atlanır (mevcut davranış).
    assert out_of_scope_files(["anything.py"], []) == []
    assert out_of_scope_files(["anything.py"], ["<belirsiz>"]) == []


def test_scan_placeholders_positives():
    files = [
        {"path": "a.py", "content": "# TODO: bitir"},
        {"path": "b.py", "content": "raise NotImplementedError()"},
        {"path": "c.py", "content": "def f():\n    pass\n"},
        {"path": "d.py", "content": "def g():\n    ...\n"},
    ]
    joined = "\n".join(scan_placeholders(files))
    assert "a.py:1" in joined and "TODO" in joined
    assert "b.py:1" in joined and "NotImplementedError" in joined
    assert "c.py:2" in joined
    assert "d.py:2" in joined


def test_scan_placeholders_no_false_positives():
    files = [
        {"path": "a.py", "content": "x = 1\n"},
        {"path": "b.py", "content": 'password = "pass"\n'},
        # `except ...: pass` aynı satırda → salt `pass` satırı değil.
        {"path": "c.py", "content": "try:\n    x()\nexcept Exception: pass\n"},
    ]
    assert scan_placeholders(files) == []


def test_scan_placeholders_ignores_malformed_items():
    assert scan_placeholders(["not-a-dict", None, 42]) == []
