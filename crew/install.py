"""Install or remove Crew's local pieces on this Mac.

Hook entries are appended beside whatever is already configured and removed
by matching Crew's exact command; nothing else in a harness's settings is
touched, and Codex's own review of new hooks is left to Codex. `--dry-run`
prints the changes without writing.
"""

import difflib
import json
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from crew import config

REPO = Path(__file__).resolve().parent.parent
EMIT = "crew-emit"
# Lifecycle edges only; routine tool activity comes from native records.
HOOK_EVENTS = {
    "claude": ("SessionStart", "SessionEnd", "Stop", "StopFailure", "Notification",
               "SubagentStart", "SubagentStop", "Elicitation", "ElicitationResult"),
    "codex": ("SessionStart", "SessionEnd"),
}
LABEL = "com.mascah.crew.{}"


def _write(path: Path, text: str, dry_run: bool) -> None:
    path = path.resolve()  # a settings file kept in a dotfiles repo stays a link to it
    old = path.read_text() if path.exists() else ""
    if old == text:
        print(f"unchanged  {path}")
        return
    diff = difflib.unified_diff(old.splitlines(), text.splitlines(), str(path), str(path), n=1,
                                lineterm="")
    print("\n".join(diff))
    if dry_run:
        return
    backup = path.with_name(path.name + ".before-crew")
    if path.exists() and not backup.exists():
        shutil.copy2(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_name(path.name + ".crew-tmp")
    scratch.write_text(text)
    if path.exists():
        shutil.copymode(path, scratch)
    os.replace(scratch, path)  # atomic: a running harness never reads half a file


def edit_hooks(settings: dict, harness: str, command: str, remove: bool) -> dict:
    """Return settings with Crew's entries added or removed; others untouched."""
    hooks = dict(settings.get("hooks") or {})
    for event in HOOK_EVENTS[harness]:
        entries = []
        for entry in hooks.get(event, []):  # take out our command only, never a neighbour
            kept = [h for h in entry.get("hooks", []) if h.get("command") != command]
            if len(kept) == len(entry.get("hooks", [])):
                entries.append(entry)
            elif kept:
                entries.append(entry | {"hooks": kept})
        if not remove:
            entries.append({"hooks": [{"type": "command", "command": command, "timeout": 1}]})
        if entries:
            hooks[event] = entries
        else:
            hooks.pop(event, None)
    result = dict(settings)
    if hooks or "hooks" in settings:
        result["hooks"] = hooks
    return result


def hooks(cfg: config.Config, home: Path, remove: bool, dry_run: bool) -> int:
    binary, journal = home / "bin" / EMIT, home / "journal.jsonl"
    if not remove and not dry_run:
        binary.parent.mkdir(parents=True, exist_ok=True)
        source = Path(__file__).with_name("emit.c")
        subprocess.run(["cc", "-O2", "-Wall", "-o", str(binary), str(source)], check=True)
    targets = {
        "claude": Path(cfg.claude_home).expanduser() / "settings.json",
        "codex": Path(cfg.codex_home).expanduser() / "hooks.json",
    }
    for harness, path in targets.items():
        if not path.parent.is_dir():
            print(f"skipped    {harness}: {path.parent} not found")
            continue
        settings = json.loads(path.read_text()) if path.exists() else {}
        command = f"'{binary}' '{journal}' {harness}"
        edited = edit_hooks(settings, harness, command, remove)
        _write(path, json.dumps(edited, indent=2, ensure_ascii=False) + "\n", dry_run)
    if not remove:
        print("Codex asks you to review new hooks before it runs them; Crew does not bypass that.")
    return 0


def hermes(cfg: config.Config, remove: bool, dry_run: bool) -> int:
    root = Path(cfg.hermes_home).expanduser()
    if not root.is_dir():
        print(f"skipped    hermes: {root} not found")
        return 0
    # Hermes loads plugins per profile: the default home and each named profile.
    for home in [root, *sorted(p for p in (root / "profiles").glob("[!.]*") if p.is_dir())]:
        target = home / "plugins" / "crew"
        print(f"{'remove' if remove else 'install'}    {target}")
        if dry_run:
            continue
        shutil.rmtree(target, ignore_errors=True)
        if not remove:
            shutil.copytree(Path(__file__).with_name("hermes_plugin"), target,
                            ignore=shutil.ignore_patterns("__pycache__"))
    if not remove:
        print("Enable it in each profile with `hermes [-p PROFILE] plugins enable crew`,"
              " then restart the Hermes gateway.")
    return 0


def launch_agent(name: str, remove: bool, dry_run: bool) -> int:
    label = LABEL.format(name)
    plist = Path.home() / "Library/LaunchAgents" / f"{label}.plist"
    log = config.home() / f"{name}.log"
    arguments = [str(REPO / ".venv/bin/python"), "-m", "crew", name, "--standby"]
    definition = {
        "Label": label,
        "ProgramArguments": arguments,
        "WorkingDirectory": str(REPO),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "ProcessType": "Background",
        # Graphical logins and SSH/background sessions alike, as Hermes's gateway does.
        "LimitLoadToSessionType": ["Aqua", "Background"],
        "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"},
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log),
    }
    domains = [f"gui/{os.getuid()}", f"user/{os.getuid()}"]
    if dry_run:
        print(f"{'remove' if remove else 'install'}    {plist}")
        return 0
    for domain in domains:  # replace any loaded copy before changing the file
        subprocess.run(["launchctl", "bootout", f"{domain}/{label}"], capture_output=True)
    if remove:
        plist.unlink(missing_ok=True)
        print(f"removed    {plist}")
        return 0
    config.home().mkdir(parents=True, exist_ok=True)
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_bytes(plistlib.dumps(definition))
    for domain in domains:
        done = subprocess.run(["launchctl", "bootstrap", domain, str(plist)], capture_output=True)
        if done.returncode == 0:
            print(f"loaded     {label} in {domain}")
            return 0
    print(f"could not load {label}: {done.stderr.decode().strip()}", file=sys.stderr)
    return 1


def main(what: str, remove: bool = False, dry_run: bool = False) -> int:
    cfg = config.load()
    if what == "hooks":
        return hooks(cfg, config.home(), remove, dry_run)
    if what == "hermes":
        return hermes(cfg, remove, dry_run)
    return launch_agent(what, remove, dry_run)
