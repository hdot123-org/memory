"""Unit tests for _guard_patterns.py extracted module."""
from memory_core.tools._guard_patterns import (
    FORBIDDEN_DIRS,
    FORBIDDEN_SUFFIXES,
    RE_CP,
    RE_DD,
    RE_HEREDOC,
    RE_INSTALL,
    RE_LN,
    RE_MKDIR,
    RE_MV,
    RE_NODE_E,
    RE_NODE_FS_WRITE,
    RE_NODE_REQUIRE_FS,
    RE_PYTHON_C,
    RE_PYTHON_OPEN,
    RE_PYTHON_PATH,
    RE_REDIRECT,
    RE_RM,
    RE_RSYNC,
    RE_TEE,
    RE_TOUCH,
    UNCERTAIN_PATH_PATTERNS,
)


def test_forbidden_suffixes_exists():
    """FORBIDDEN_SUFFIXES is a tuple of strings."""
    assert isinstance(FORBIDDEN_SUFFIXES, tuple)
    assert len(FORBIDDEN_SUFFIXES) > 0


def test_forbidden_suffixes_content():
    """FORBIDDEN_SUFFIXES contains expected file extensions."""
    expected = (".sql", ".bak", ".sqlite", ".db", ".dump", ".sql.gz")
    assert FORBIDDEN_SUFFIXES == expected


def test_forbidden_dirs_exists():
    """FORBIDDEN_DIRS is a frozenset."""
    assert isinstance(FORBIDDEN_DIRS, frozenset)
    assert len(FORBIDDEN_DIRS) > 0


def test_forbidden_dirs_content():
    """FORBIDDEN_DIRS contains expected directory names."""
    assert FORBIDDEN_DIRS == frozenset({"backups"})


def test_re_mv_matches_git_mv():
    """RE_MV matches 'git mv source dest'."""
    m = RE_MV.match("git mv old.py new.py")
    assert m is not None
    assert m.group(1) == "old.py new.py"


def test_re_mv_matches_plain_mv():
    """RE_MV matches 'mv source dest'."""
    m = RE_MV.match("mv a.txt b.txt")
    assert m is not None
    assert m.group(1) == "a.txt b.txt"


def test_re_rm_matches():
    """RE_RM matches 'rm -rf path'."""
    m = RE_RM.match("rm -rf /tmp/test")
    assert m is not None
    assert m.group(1) == "/tmp/test"


def test_re_cp_matches():
    """RE_CP matches 'cp -r src dest'."""
    m = RE_CP.match("cp -r src dest")
    assert m is not None
    assert m.group(1) == "src dest"


def test_re_mkdir_matches():
    """RE_MKDIR matches 'mkdir -p path'."""
    m = RE_MKDIR.match("mkdir -p /tmp/newdir")
    assert m is not None
    assert m.group(1) == "/tmp/newdir"


def test_re_touch_matches():
    """RE_TOUCH matches 'touch file.txt'."""
    m = RE_TOUCH.match("touch file.txt")
    assert m is not None
    assert m.group(1) == "file.txt"


def test_re_python_c_matches():
    """RE_PYTHON_C matches 'python -c \"code\"'."""
    m = RE_PYTHON_C.match('python -c "print(1)"')
    assert m is not None
    assert "print(1)" in m.group(1)


def test_re_python_open_matches():
    """RE_PYTHON_OPEN matches open() calls."""
    m = RE_PYTHON_OPEN.search('open("test.txt", "w")')
    assert m is not None
    assert m.group(1) == "test.txt"


def test_re_python_path_matches():
    """RE_PYTHON_PATH matches Path() calls."""
    m = RE_PYTHON_PATH.search('Path("/tmp/file.txt")')
    assert m is not None
    assert m.group(1) == "/tmp/file.txt"


def test_re_redirect_matches():
    """RE_REDIRECT matches shell redirects."""
    m = RE_REDIRECT.search("echo test > output.txt")
    assert m is not None
    assert m.group(1) == "output.txt"


def test_re_tee_matches():
    """RE_TEE matches 'tee file'."""
    m = RE_TEE.match("echo test | tee output.txt")
    assert m is not None


def test_re_dd_matches():
    """RE_DD matches 'dd of=file'."""
    m = RE_DD.match("dd if=/dev/zero of=output.bin")
    assert m is not None
    assert m.group(1) == "output.bin"


def test_re_install_matches():
    """RE_INSTALL matches 'install src dest'."""
    m = RE_INSTALL.match("install -m 755 script /usr/local/bin")
    assert m is not None
    # The regex captures everything after flags, including "755 script /usr/local/bin"
    # The actual path splitting happens in _split_shell_args which extracts the last arg
    assert "script" in m.group(1)
    assert "/usr/local/bin" in m.group(1)


def test_re_ln_matches():
    """RE_LN matches 'ln -s target link'."""
    m = RE_LN.match("ln -s /tmp/target /tmp/link")
    assert m is not None
    assert m.group(1) == "/tmp/target /tmp/link"


def test_uncertain_path_patterns_exists():
    """UNCERTAIN_PATH_PATTERNS is a list of regex patterns."""
    assert isinstance(UNCERTAIN_PATH_PATTERNS, list)
    assert len(UNCERTAIN_PATH_PATTERNS) > 0


def test_uncertain_path_patterns_content():
    """UNCERTAIN_PATH_PATTERNS contains wildcard and variable patterns."""
    patterns_str = " ".join(UNCERTAIN_PATH_PATTERNS)
    assert "\\*" in patterns_str  # wildcard
    assert "\\$" in patterns_str  # variable


def test_all_regex_patterns_are_compiled():
    """All RE_* constants are compiled regex objects."""
    patterns = [
        RE_MV, RE_RM, RE_CP, RE_MKDIR, RE_TOUCH,
        RE_PYTHON_C, RE_REDIRECT, RE_TEE, RE_DD,
        RE_INSTALL, RE_LN, RE_PYTHON_OPEN, RE_PYTHON_PATH,
        RE_NODE_FS_WRITE, RE_NODE_REQUIRE_FS, RE_HEREDOC,
        RE_RSYNC, RE_NODE_E,
    ]
    for p in patterns:
        assert hasattr(p, "match") or hasattr(p, "search")
