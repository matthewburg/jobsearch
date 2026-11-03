"""Set up the job finder on this computer, wherever the kit folder lives.

- Checks the Python version (3.11+; stdlib only, nothing to pip install).
- Creates profile/ and samples/ from templates/ (copies missing files only;
  never overwrites anything you've filled in) and job-finder/state/.
- Adds the job-finder MCP server to <project>/.mcp.json and the report
  preview to <project>/.claude/launch.json, with absolute paths to this kit.
  Other entries in those files are kept as they are.

<project> is the folder you open Claude sessions in (default: the kit folder).

  python -I job-finder/install.py                      # set up in the kit folder
  python -I job-finder/install.py --project ..         # register in a parent folder
  python -I job-finder/install.py --dry-run            # show what would change
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

JF = Path(__file__).resolve().parent
KIT = JF.parent
PORT = 8765


def python_command() -> str:
    """'python' when that's the interpreter running this (survives upgrades), else the full path."""
    found = shutil.which("python")
    if found and Path(found).resolve() == Path(sys.executable).resolve():
        return "python"
    return Path(sys.executable).as_posix()


def copy_missing(src: Path, dst: Path, dry: bool, out: list[str]):
    for f in sorted(src.rglob("*")):
        if f.is_dir():
            continue
        target = dst / f.relative_to(src)
        if target.exists():
            continue
        out.append(f"create {target.relative_to(KIT).as_posix()}")
        if not dry:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)


def merge_json(path: Path, key: str, update, dry: bool, out: list[str]):
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    before = json.dumps(data, sort_keys=True)
    update(data.setdefault(key, {} if key == "mcpServers" else []))
    if json.dumps(data, sort_keys=True) == before:
        out.append(f"unchanged {path}")
        return
    out.append(f"{'update' if path.exists() else 'create'} {path}")
    if not dry:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", type=Path, default=KIT, help="folder you open Claude in (default: the kit)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    project = args.project.resolve()
    dry = args.dry_run

    if sys.version_info < (3, 11):
        print(f"Python 3.11+ needed; this is {sys.version.split()[0]}.")
        return 1

    out: list[str] = []
    copy_missing(KIT / "templates" / "profile", KIT / "profile", dry, out)
    copy_missing(KIT / "templates" / "samples", KIT / "samples", dry, out)
    if not (JF / "state").exists():
        out.append("create job-finder/state/")
        if not dry:
            (JF / "state").mkdir()

    py = python_command()
    server = {"type": "stdio", "command": py, "args": ["-I", (JF / "mcp" / "server.py").as_posix()]}
    merge_json(project / ".mcp.json", "mcpServers",
               lambda servers: servers.__setitem__("job-finder", server), dry, out)

    preview = {"name": "job-report", "runtimeExecutable": py,
               "runtimeArgs": ["-I", (JF / "app" / "server.py").as_posix()], "port": PORT}

    def add_preview(configs: list):
        configs[:] = [c for c in configs if c.get("name") != "job-report"] + [preview]

    launch = project / ".claude" / "launch.json"
    if not launch.exists():
        out.append(f"create {launch}")
        if not dry:
            launch.parent.mkdir(parents=True, exist_ok=True)
            launch.write_text(json.dumps({"version": "0.0.1", "configurations": [preview]}, indent=2) + "\n",
                              encoding="utf-8")
    else:
        merge_json(launch, "configurations", add_preview, dry, out)

    print(("Would do:" if dry else "Done:") + "\n  " + "\n  ".join(out))
    print(f"\nKit: {KIT}\nClaude project folder: {project}\nPython command: {py}")
    print("\nNext: fill in profile/ (SETUP.md, step 3), then start a new Claude session in the project folder"
          " and approve 'job-finder'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
