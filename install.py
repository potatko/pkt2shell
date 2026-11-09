#!/usr/bin/env python3
"""Install the pkt2shell agent skill on this computer.

Usage:
    python3 install.py              install for Claude Code and Codex
    python3 install.py --claude     Claude Code only  (~/.claude/skills/packet-tracer/)
    python3 install.py --codex      Codex only        (~/.agents/skills/packet-tracer/)
    python3 install.py --uninstall  remove the skill from both locations

    --output new        completed activity is written to "<name> - completed.pka" (default)
    --output overwrite  completed activity replaces the original file (a backup is kept)
    If --output is omitted, the mode of an existing installation is kept.

On Windows use `py install.py`. Re-run after `git pull` or after moving this folder.
"""
import argparse
import importlib.util
import os
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
SKILL = "packet-tracer"
TARGETS = {
    "Claude Code": Path.home() / ".claude" / "skills" / SKILL,
    "Codex": Path.home() / ".agents" / "skills" / SKILL,
}


def python_cmd():
    if os.name == "nt":
        return "py -3" if shutil.which("py") else "python"
    return "python3"


MODE_RE = re.compile(r"Default output mode on this computer: \*\*`(new|overwrite)`\*\*")


def current_mode():
    """Output mode of an existing installation, if any."""
    for t in TARGETS.values():
        f = t / "SKILL.md"
        if f.exists():
            m = MODE_RE.search(f.read_text(encoding="utf-8"))
            if m:
                return m.group(1)
    return None


def self_test():
    spec = importlib.util.spec_from_file_location("ptcrypto", REPO / "tools" / "ptcrypto.py")
    ptcrypto = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ptcrypto)
    # Twofish known-answer test: all-zero 128-bit key and block
    if ptcrypto.Twofish(bytes(16)).encrypt_block(bytes(16)).hex().upper() != "9F589F5CF6122C32B6BFEC2F2AE8C35A":
        sys.exit("Self-test failed: the Twofish implementation returned an incorrect result.")


def main():
    ap = argparse.ArgumentParser(description="Install the pkt2shell skill for Claude Code and/or Codex.")
    ap.add_argument("--claude", action="store_true", help="install for Claude Code only")
    ap.add_argument("--codex", action="store_true", help="install for Codex only")
    ap.add_argument("--uninstall", action="store_true", help="remove the installed skill")
    ap.add_argument("--output", choices=("new", "overwrite"),
                    help="default output mode: new file (default) or overwrite the original")
    a = ap.parse_args()

    if sys.version_info < (3, 8):
        sys.exit("Python 3.8 or newer is required.")

    chosen = [name for name, flag in (("Claude Code", a.claude), ("Codex", a.codex)) if flag] or list(TARGETS)

    if a.uninstall:
        for name in chosen:
            f = TARGETS[name] / "SKILL.md"
            if f.exists():
                f.unlink()
                try:
                    TARGETS[name].rmdir()
                except OSError:
                    pass
                print(f"Removed  {name}: {f}")
        return

    self_test()
    repo = REPO.as_posix()
    pkt = f'{python_cmd()} -I "{repo}/tools/pkt.py"'
    text = (REPO / "skill" / "SKILL.md").read_text(encoding="utf-8")
    mode = a.output or current_mode() or "new"
    text = text.replace("{{REPO}}", repo).replace("{{PKT}}", pkt).replace("{{OUTPUT_MODE}}", mode)

    for name in chosen:
        TARGETS[name].mkdir(parents=True, exist_ok=True)
        (TARGETS[name] / "SKILL.md").write_text(text, encoding="utf-8")
        print(f"Installed  {name}: {TARGETS[name] / 'SKILL.md'}")
    (REPO / "labs").mkdir(exist_ok=True)

    print(f"Output mode:  {mode}" + ("  (original is backed up, then overwritten)" if mode == "overwrite"
                                       else '  (result goes to "<name> - completed.pka")'))
    print(f"Tool command: {pkt}")
    print("Start a new agent session in any folder and ask, for example:")
    print('    Complete the Packet Tracer activity "C:/Users/me/Downloads/lab.pka"')


if __name__ == "__main__":
    main()
