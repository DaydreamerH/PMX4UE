"""Create an isolated blank host for a packaged-plugin API smoke test."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--engine", required=True, type=Path)
parser.add_argument("--plugin", required=True, type=Path)
parser.add_argument("--output", required=True, type=Path)
args = parser.parse_args()
if args.output.exists():
    raise SystemExit("Output exists: choose a fresh verification folder")
args.output.mkdir(parents=True)
project = args.output / "Blank.uproject"
project.write_text(json.dumps({"FileVersion": 3, "Plugins": [{"Name": "PMX4UE", "Enabled": True}]}), encoding="utf-8")
shutil.copytree(args.plugin, args.output / "Plugins/PMX4UE", ignore=shutil.ignore_patterns("Intermediate", "HostProject"))
root = Path(__file__).resolve().parents[1]
command = [str(args.engine / "Engine/Binaries/Win64/UnrealEditor-Cmd.exe"), str(project.resolve()),
           "-run=pythonscript", "-script=" + str(root / "tools/ue_probe.py"), "-unattended", "-nop4", "-nosplash"]
with (args.output / "probe.log").open("w", encoding="utf-8") as log:
    result = subprocess.run(command, env={**os.environ, "PMX4UE_PROBE_OUTPUT": str((args.output / "probe.json").resolve())},
                            stdout=log, stderr=subprocess.STDOUT, timeout=600,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
print("exit", result.returncode, "report", args.output / "probe.json")
raise SystemExit(result.returncode)
