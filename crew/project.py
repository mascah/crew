"""Repository identity candidates for a working folder.

A folder yields keys the service resolves to a persisted Crew project ID:
the machine-scoped Git common directory (joins worktrees locally) and, when
`origin` is a single recognized hosted URL, its normalized form (joins clones
across machines). Anything ambiguous stays machine-local until mapped.
"""

import os
import re
import subprocess
from functools import lru_cache
from urllib.parse import urlsplit

from crew.model import ProjectRef

# A hosted remote signs in as `git`; `alice@nas:repo` is a path in Alice's home.
_SCP = re.compile(r"^(?:git@)?([^@:/\s]+):(?!/)(.+)$")


def normalize_origin(url: str) -> str | None:
    """`host/path` for a recognized SSH/HTTPS remote, else None.

    Only hostname case, credentials, default ports and a trailing `.git` are
    normalized; path case and everything provider-specific are preserved.
    """
    url = url.strip()
    if "://" in url:
        parts = urlsplit(url)
        if parts.scheme not in ("ssh", "https", "http", "git"):
            return None
        try:
            port = parts.port
        except ValueError:
            return None
        if port not in (None, 22, 443, 80, 9418):
            return None
        host, path = parts.hostname or "", parts.path
    elif m := _SCP.match(url):
        host, path = m.group(1), m.group(2)
    else:
        return None
    path = path.strip("/").removesuffix(".git")
    # An undotted host is an SSH config alias or localhost: not a shared identity.
    if "." not in host or not path:
        return None
    return f"{host.lower()}/{path}"


def _git(cwd: str, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", cwd, *args], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def identify(machine_id: str, cwd: str) -> ProjectRef:
    folder = probe = os.path.realpath(cwd)
    while not os.path.isdir(probe) and probe != os.path.dirname(probe):
        probe = os.path.dirname(probe)  # a removed worktree folder still sat inside its repository
    common = _git(probe, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not common:
        return ProjectRef(
            keys=[f"folder:{machine_id}:{folder}"], name=os.path.basename(folder), checkout=folder
        )
    common = os.path.realpath(common)
    keys = [f"git:{machine_id}:{common}"]
    name = os.path.basename(common.removesuffix("/.git")) or common
    urls = (_git(probe, "remote", "get-url", "--all", "origin") or "").split()
    if len(urls) == 1 and (origin := normalize_origin(urls[0])):
        keys.append(f"origin:{origin}")
        name = origin.rsplit("/", 1)[-1]
    checkout = folder if probe != folder else _git(folder, "rev-parse", "--show-toplevel") or folder
    return ProjectRef(keys=keys, name=name, checkout=checkout)


# ponytail: cached for the collector's lifetime, so a changed remote is seen on
# restart; add a TTL if remotes change often enough to matter.
identify_cached = lru_cache(maxsize=2048)(identify)
