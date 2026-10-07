import subprocess

import pytest

from crew.project import identify, normalize_origin


def git(path, *args):
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def repo(path, origin=None):
    path.mkdir(parents=True)
    git(path, "init", "-q")
    git(path, "-c", "user.name=t", "-c", "user.email=t@example.invalid",
        "commit", "--allow-empty", "-qm", "fixture")
    if origin:
        git(path, "remote", "add", "origin", origin)
    return path


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("git@github.com:mascah/crew.git", "github.com/mascah/crew"),
        ("https://github.com/mascah/crew", "github.com/mascah/crew"),
        ("https://user:secret@GitHub.com/mascah/crew.git/", "github.com/mascah/crew"),
        ("ssh://git@github.com:22/mascah/crew.git", "github.com/mascah/crew"),
        ("git@github.com:Mascah/crew.git", "github.com/Mascah/crew"),  # path case kept
        ("git@gh-work:mascah/crew.git", None),  # SSH alias
        ("alice@nas.example.com:crew.git", None),  # a path in one user's home directory
        ("/srv/git/crew.git", None),
        ("file:///srv/git/crew.git", None),
        ("../crew", None),
        ("ssh://git@git.example.com:2222/team/crew.git", None),  # non-default port
    ],
)
def test_normalize_origin(url, expected):
    assert normalize_origin(url) == expected


def test_clones_and_worktrees_share_an_identity(tmp_path):
    a = repo(tmp_path / "a/crew", "git@github.com:mascah/crew.git")
    wt = tmp_path / "crew-wt"
    git(a, "worktree", "add", "-q", "--detach", str(wt))
    b = repo(tmp_path / "b/crew", "https://github.com/mascah/crew")
    ida, idw, idb = identify("mini", str(a)), identify("mini", str(wt)), identify("book", str(b))
    assert ida.keys == idw.keys  # worktree: same common dir and origin
    assert ida.keys[1] == idb.keys[1] == "origin:github.com/mascah/crew"
    assert ida.keys[0] != idb.keys[0]  # local keys stay machine-scoped
    assert idw.checkout.endswith("crew-wt") and ida.name == "crew"


def test_ambiguous_identities_stay_distinct(tmp_path):
    other = identify("mini", str(repo(tmp_path / "c/crew", "git@github.com:unrelated/crew.git")))
    fork = identify("mini", str(repo(tmp_path / "d/crew", "git@github.com:someone/crew.git")))
    git(tmp_path / "d/crew", "remote", "add", "upstream", "git@github.com:unrelated/crew.git")
    assert other.keys[1] != fork.keys[1]  # an upstream remote does not merge a fork

    for origin in (None, "git@gh-work:mascah/crew.git", str(tmp_path / "c/crew")):
        ref = identify("mini", str(repo(tmp_path / f"e{hash(origin)}/crew", origin)))
        assert len(ref.keys) == 1 and ref.keys[0].startswith("git:mini:")

    multi = repo(tmp_path / "f/crew", "git@github.com:mascah/crew.git")
    git(multi, "remote", "set-url", "--add", "origin", "git@gitlab.com:mascah/crew.git")
    assert len(identify("mini", str(multi)).keys) == 1


def test_a_removed_worktree_still_belongs_to_its_repository(tmp_path):
    main = repo(tmp_path / "crew", "git@github.com:mascah/crew.git")
    gone = identify("mini", str(main / ".claude/worktrees/task-1"))
    assert gone.keys == identify("mini", str(main)).keys
    assert gone.checkout.endswith("worktrees/task-1")
    assert identify("mini", str(tmp_path / "removed/scratch")).keys[0].startswith("folder:mini:")


def test_submodule_is_its_own_repository(tmp_path):
    lib = repo(tmp_path / "lib", "git@github.com:mascah/lib.git")
    top = repo(tmp_path / "top", "git@github.com:mascah/top.git")
    git(top, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(lib), "lib")
    git(top / "lib", "remote", "set-url", "origin", "git@github.com:mascah/lib.git")
    sub = identify("mini", str(top / "lib"))
    assert sub.keys[1] == "origin:github.com/mascah/lib"
    assert sub.keys != identify("mini", str(top)).keys


def test_folder_outside_git(tmp_path):
    (tmp_path / "notes").mkdir()
    ref = identify("mini", str(tmp_path / "notes"))
    assert ref.keys == [f"folder:mini:{(tmp_path / 'notes').resolve()}"]
    assert ref.name == "notes"
