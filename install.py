#!/usr/bin/env python3
"""Install the pkt2shell Claude Code skill for this computer.

Usage:  python3 install.py        (Windows: py install.py)

Writes ~/.claude/skills/packet-tracer/SKILL.md with the paths of this repo filled in,
then runs a quick self-test of the Packet Tracer file codec. Re-run after `git pull`.
"""
import importlib.util
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent


def python_cmd():
    if os.name == "nt":
        return "py -3" if shutil.which("py") else "python"
    return "python3"


def main():
    if sys.version_info < (3, 8):
        sys.exit("Python 3.8 or newer is required.")

    # self-test: Twofish known-answer test (all-zero 128-bit key and block)
    spec = importlib.util.spec_from_file_location("ptcrypto", REPO / "tools" / "ptcrypto.py")
    ptcrypto = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ptcrypto)
    ct = ptcrypto.Twofish(bytes(16)).encrypt_block(bytes(16)).hex().upper()
    if ct != "9F589F5CF6122C32B6BFEC2F2AE8C35A":
        sys.exit("self-test failed: Twofish implementation returned a wrong result")

    repo = REPO.as_posix()
    pkt = f'{python_cmd()} -I "{repo}/tools/pkt.py"'
    text = (REPO / "skill" / "SKILL.md").read_text(encoding="utf-8")
    text = text.replace("{{REPO}}", repo).replace("{{PKT}}", pkt)

    dest = Path.home() / ".claude" / "skills" / "packet-tracer"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "SKILL.md").write_text(text, encoding="utf-8")
    (REPO / "labs").mkdir(exist_ok=True)

    print(f"OK  skill installed: {dest / 'SKILL.md'}")
    print(f"    tool command:    {pkt}")
    print("Open a new Claude Code session anywhere and say e.g.:")
    print('    sprav aktivitu "C:/Users/me/Downloads/lab.pka"')


if __name__ == "__main__":
    main()
