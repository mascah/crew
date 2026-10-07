import json
import os
import subprocess
from pathlib import Path

import pytest

from crew import config, install
from crew.journal import Journal


def test_hook_entries_are_added_beside_existing_ones_and_removed_cleanly():
    mine = {"hooks": [{"type": "command", "command": "/usr/local/bin/my-notify"}]}
    settings = {"model": "x", "hooks": {"Stop": [mine], "PreToolUse": [mine]},
                "permissions": {"allow": ["Bash(ls:*)"]}}
    command = "'/crew/bin/crew-emit' '/crew/journal.jsonl' claude"
    added = install.edit_hooks(settings, "claude", command, remove=False)
    assert added["hooks"]["Stop"][0] == mine and len(added["hooks"]["Stop"]) == 2
    assert added["hooks"]["PreToolUse"] == [mine]  # no routine tool hooks
    assert "PermissionRequest" not in added["hooks"]  # policy callbacks are never observed
    assert {k: v for k, v in added.items() if k != "hooks"} == {
        k: v for k, v in settings.items() if k != "hooks"}
    assert install.edit_hooks(added, "claude", command, remove=False) == added  # idempotent
    assert install.edit_hooks(added, "claude", command, remove=True) == settings
    shared = {"hooks": {"Stop": [{"hooks": [mine["hooks"][0], {"type": "command",
                                                               "command": command}]},
                                 {"hooks": [{"type": "command", "command": "screw-emitter"}]}]}}
    left = install.edit_hooks(shared, "claude", command, remove=True)["hooks"]["Stop"]
    assert left == [mine, {"hooks": [{"type": "command", "command": "screw-emitter"}]}]
    assert install.edit_hooks({}, "codex", command, remove=True) == {}
    assert set(install.edit_hooks({}, "codex", command, remove=False)["hooks"]) == {
        "SessionStart", "SessionEnd"}


def test_installed_hook_command_runs_and_uninstall_restores_the_files(tmp_path, monkeypatch):
    monkeypatch.setenv("CREW_HOME", str(tmp_path / "crew"))
    claude, codex = tmp_path / "claude", tmp_path / "codex"
    claude.mkdir()
    codex.mkdir()
    original = json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "true"}]}]},
                           "env": {"A": "1"}}, indent=2) + "\n"
    dotfiles = tmp_path / "dotfiles/claude-settings.json"  # kept elsewhere, linked into place
    dotfiles.parent.mkdir()
    dotfiles.write_text(original)
    dotfiles.chmod(0o600)
    (claude / "settings.json").symlink_to(dotfiles)
    cfg = config.Config(claude_home=str(claude), codex_home=str(codex),
                        hermes_home=str(tmp_path / "hermes"))

    install.hooks(cfg, tmp_path / "crew", remove=False, dry_run=True)
    assert (claude / "settings.json").read_text() == original
    assert not (codex / "hooks.json").exists()

    install.hooks(cfg, tmp_path / "crew", remove=False, dry_run=False)
    assert dotfiles.with_name(dotfiles.name + ".before-crew").read_text() == original
    assert (claude / "settings.json").is_symlink() and dotfiles.stat().st_mode & 0o777 == 0o600
    installed = json.loads((claude / "settings.json").read_text())
    command = installed["hooks"]["Notification"][0]["hooks"][0]["command"]
    payload = json.dumps({"hook_event_name": "Notification", "session_id": "s",
                          "notification_type": "permission_prompt", "message": "private"})
    done = subprocess.run(command, shell=True, input=payload.encode(), capture_output=True,
                          check=True, env={"PATH": os.environ["PATH"]})
    assert done.stdout == b"{}\n"
    [event] = Journal(tmp_path / "crew/journal.jsonl").read()
    assert (event["harness"], event["notification_type"]) == ("claude", "permission_prompt")
    assert "message" not in event
    assert set(json.loads((codex / "hooks.json").read_text())["hooks"]) == {
        "SessionStart", "SessionEnd"}

    install.hooks(cfg, tmp_path / "crew", remove=True, dry_run=False)
    assert (claude / "settings.json").read_text() == original
    assert json.loads((codex / "hooks.json").read_text()) == {"hooks": {}}


def test_hermes_plugin_install_and_removal(tmp_path):
    cfg = config.Config(hermes_home=str(tmp_path / "hermes"))
    assert install.hermes(cfg, remove=False, dry_run=False) == 0  # no Hermes here: skipped
    (tmp_path / "hermes/profiles/factory").mkdir(parents=True)
    (tmp_path / "hermes/profiles/.deleted").mkdir()  # Hermes's own bookkeeping, not a profile
    install.hermes(cfg, remove=False, dry_run=False)
    plugin = tmp_path / "hermes/plugins/crew"
    assert {p.name for p in plugin.iterdir()} == {"__init__.py", "plugin.yaml"}
    assert (tmp_path / "hermes/profiles/factory/plugins/crew/plugin.yaml").exists()  # per profile
    assert not list((tmp_path / "hermes/profiles/.deleted").iterdir())
    source = Path(plugin / "__init__.py").read_text()
    assert "from crew" not in source and "import crew" not in source  # runs inside Hermes
    install.hermes(cfg, remove=True, dry_run=False)
    assert not plugin.exists() and not (tmp_path / "hermes/profiles/factory/plugins/crew").exists()


def test_settings_of_the_wrong_type_are_refused(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('viewer_logins = "me@example.com"\n')
    with pytest.raises(ValueError, match="viewer_logins must be a list"):
        config.load(path)
    path.write_text('viewer_logins = ["me@example.com"]\nstale_seconds = 45\n')
    assert config.load(path).stale_seconds == 45
