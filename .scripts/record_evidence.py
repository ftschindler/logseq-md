#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Try a skill on a real assistant, and record what it did into tests/evidence/.

Ported from ftschindler/agent-kits. The suite can tell you every command in the
skill runs; only asking a model can tell you it reaches for them.

It runs against **the assistant you already have authenticated**, rather than
installing one: a CI runner has no credentials, and opencode's free models are
out of quota there, so the run happens here, on your machine, and what CI sees
is the recording. The offline half of the contract is `.scripts/check_evidence.py`, which fails the
build when a kit has changed since its recording.

The agent itself is disposable. HOME and every XDG directory point into a temp
tree holding only the skill under test, so the reply is a reaction to that kit and
not to whatever else is installed on this machine. Your opencode credentials are
the one thing copied in, read-only, and they are never written to the recording.

Each probe gets a fresh copy of the fixture graph its probes file names, as
`graph/` in the agent's working directory, and an assertion can look at three
things: the reply (the default), the tool calls the agent made (`"over":
"commands"`), or a file of that graph after the run (`"over": "file:<path>"`).
The agent reaches the tool through `uvx logseq-md` as a user would, so what is
recorded is the published release, not this checkout.

Usage:
  record_evidence.py <skill> [--model PROVIDER/MODEL] [--keep]

  <skill>    a directory under skills/
  --model    passed to `opencode run --model`; defaults to opencode's own
  --keep     leave the sandbox on disk and print how to enter it
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROBES_DIR = REPO_ROOT / "tests" / "probes"
EVIDENCE_DIR = REPO_ROOT / "tests" / "evidence"

SCHEMA_VERSION = 1

# One allowance per probe. A run is a model driving tools, so its duration swings
# with the path it picks; a genuinely stuck one is caught here rather than left.
RUN_TIMEOUT = 600

NOT_PART_OF_A_KIT = ("__pycache__", ".ruff_cache", ".pytest_cache")
# The release job rewrites VERSION on every merge, and a recording made stale by
# every release would be a check nobody could keep green. It says nothing to a model.
NOT_COVERED = ("VERSION",)

# Variables that would point the sandbox back at the real setup. Redirecting HOME
# is not enough on its own: OPENCODE_CONFIG_DIR overrides config lookup outright,
# and PWD arrives stale and absolute, naming the repository under test.
LEAKY_PREFIX = "OPENCODE"
LEAKY_VARS = ("PWD", "OLDPWD")


def fail(message: str) -> None:
    sys.exit(f"record_evidence: {message}")


def skill_parts(name: str) -> tuple[Path, list[Path]]:
    """Locate a skill by name: its directory, and every file the evidence covers."""
    skill = next((p.parent for p in (REPO_ROOT / "skills").rglob("SKILL.md") if p.parent.name == name), None)
    if skill is None:
        fail(f"no skill called {name!r} under skills/")
        raise AssertionError  # unreachable; keeps the type checker honest
    files = [
        path
        for path in sorted(skill.rglob("*"))
        if path.is_file() and path.name not in NOT_COVERED and not any(part in NOT_PART_OF_A_KIT for part in path.parts)
    ]
    files.append(PROBES_DIR / f"{name}.json")
    return skill, sorted(files)


def build_sandbox(root: Path, skill: Path) -> tuple[Path, Path, dict[str, str]]:
    """A home holding only this skill, with the real opencode credentials copied in."""
    home = root / "home"
    work = home / "work"
    work.mkdir(parents=True, exist_ok=True)

    env = {k: v for k, v in os.environ.items() if not k.startswith(LEAKY_PREFIX) and k not in LEAKY_VARS}
    env.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "XDG_STATE_HOME": str(home / ".local" / "state"),
            "PWD": str(work),
        }
    )

    destination = home / ".agents" / "skills" / skill.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(skill, destination, ignore=shutil.ignore_patterns(*NOT_PART_OF_A_KIT))

    config_dir = home / ".config" / "opencode"
    config_dir.mkdir(parents=True, exist_ok=True)
    # `opencode run` is non-interactive, so a permission prompt is auto-rejected,
    # and the skills sit outside the working directory.
    (config_dir / "opencode.json").write_text(
        json.dumps(
            {"$schema": "https://opencode.ai/config.json", "permission": {"external_directory": "allow"}},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    copy_credentials(home, env)
    return home, work, env


def copy_credentials(home: Path, env: dict[str, str]) -> None:
    """Copy this machine's opencode credentials into the sandbox.

    The whole point of this layer is a run against the assistant you have already
    authenticated, so the sandbox needs the token and nothing else from your real
    profile. It is copied rather than shared, so the run cannot write to it.
    """
    real_data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    for relative in ("opencode/auth.json", "opencode/mcp-auth.json"):
        source = real_data / relative
        if not source.is_file():
            continue
        target = Path(env["XDG_DATA_HOME"]) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o600)
    if not (Path(env["XDG_DATA_HOME"]) / "opencode" / "auth.json").is_file():
        fail(
            "no opencode credentials found. Log in with `opencode auth login` first: "
            "this layer runs against the assistant you have already authenticated."
        )


def events(stdout: str) -> list[dict]:
    """The JSON events of an `opencode run --format json` stream."""
    found = []
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            found.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return found


def tool_calls(stdout: str) -> list[str]:
    """Every tool the assistant called, as `<tool> <input as JSON>`, in order."""
    return [
        f"{event['part'].get('tool')} {json.dumps(event['part'].get('state', {}).get('input', {}), sort_keys=True)}"
        for event in events(stdout)
        if event.get("type") == "tool_use" and isinstance(event.get("part"), dict)
    ]


def assistant_text(stdout: str) -> str:
    """The assistant's own words, out of the JSON event stream."""
    chunks = []
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        part = event.get("part", {})
        if event.get("type") == "text" and "text" in part:
            chunks.append(part["text"])
    return "\n".join(chunks)


def scrub(text: str, *, home: Path) -> str:
    """Remove this machine from the recording.

    A transcript carries the sandbox path, which carries the username, and a
    recording committed to a shared repository has no business naming either.
    """
    text = text.replace(str(home), "<sandbox>")
    text = text.replace(json.dumps(str(home))[1:-1], "<sandbox>")
    text = text.replace(str(REPO_ROOT), "<repo>")
    try:
        user = getpass.getuser()
    except (KeyError, OSError):  # pragma: no cover - a machine with no login name
        user = ""
    if user:
        text = re.sub(rf"\b{re.escape(user)}\b", "<user>", text)
    return text


def evaluate(assertion: dict, reply: str) -> tuple[bool, str]:
    """Run one assertion against a reply. Returns the outcome and what was seen."""
    haystack = reply.lower()
    kind = assertion.get("kind")

    if kind == "contains_none":
        hits = [needle for needle in assertion["values"] if needle.lower() in haystack]
        return not hits, ("none present" if not hits else f"present: {', '.join(hits)}")

    if kind == "contains_all":
        missing = [needle for needle in assertion["values"] if needle.lower() not in haystack]
        return not missing, ("all present" if not missing else f"missing: {', '.join(missing)}")

    if kind == "contains_any":
        hits = [needle for needle in assertion["values"] if needle.lower() in haystack]
        return bool(hits), (f"present: {', '.join(hits)}" if hits else "none of them present")

    fail(f"unknown assertion kind {kind!r}")
    raise AssertionError  # unreachable; keeps the type checker honest


def haystack_for(assertion: dict, *, reply: str, commands: list[str], graph: Path) -> str:
    """What an assertion looks at: the reply, the tool calls, or a file of the graph."""
    over = assertion.get("over", "reply")
    if over == "reply":
        return reply
    if over == "commands":
        return "\n".join(commands)
    if over.startswith("file:"):
        path = graph / over.removeprefix("file:")
        return path.read_bytes().decode("utf-8") if path.is_file() else ""
    fail(f"unknown assertion target {over!r}")
    raise AssertionError  # unreachable; keeps the type checker honest


def run_probe(opencode: str, probe: dict, *, work: Path, env: dict[str, str], model: str | None) -> dict:
    command = [opencode, "run", "--format", "json"]
    if model:
        command += ["--model", model]
    command.append(probe["prompt"])

    print(f"  asking: {probe['prompt'][:70]}...", file=sys.stderr)
    completed = subprocess.run(
        command,
        cwd=work,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT,
        check=False,
    )
    if completed.returncode != 0:
        fail(f"`opencode run` exited {completed.returncode}:\n{completed.stderr.strip()}")
    return {"reply": assistant_text(completed.stdout), "commands": tool_calls(completed.stdout)}


def opencode_version(opencode: str) -> str:
    completed = subprocess.run([opencode, "--version"], capture_output=True, text=True, check=False)
    return completed.stdout.strip() or "unknown"


def git_identity() -> str:
    def config(key: str) -> str:
        return subprocess.run(
            ["git", "config", key], cwd=REPO_ROOT, capture_output=True, text=True, check=False
        ).stdout.strip()

    return f"{config('user.name')} <{config('user.email')}>".strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kit", help="a directory under skills/")
    parser.add_argument("--model", help="passed to `opencode run --model`")
    parser.add_argument("--keep", action="store_true", help="leave the sandbox on disk")
    args = parser.parse_args()

    opencode = shutil.which("opencode")
    if opencode is None:
        fail("`opencode` is not on PATH. This layer runs against your own installed assistant.")

    probes_path = PROBES_DIR / f"{args.kit}.json"
    if not probes_path.is_file():
        fail(f"no probes at {probes_path.relative_to(REPO_ROOT).as_posix()}; write them before recording")
    document = json.loads(probes_path.read_text(encoding="utf-8"))
    probes = document["probes"]
    fixture = REPO_ROOT / document["graph"]
    if not (fixture / "logseq" / "config.edn").is_file():
        fail(f"{document['graph']} is not a fixture graph")

    skill, files = skill_parts(args.kit)

    runs = []
    outcome = "pass"
    for probe in probes:
        # A fresh sandbox per probe, so one probe's writes are not the next one's graph.
        root = Path(tempfile.mkdtemp(prefix=f"evidence-{args.kit}-"))
        home, work, env = build_sandbox(root, skill)
        graph = work / "graph"
        shutil.copytree(fixture, graph)
        print(f"sandbox at {root}", file=sys.stderr)

        result = run_probe(opencode, probe, work=work, env=env, model=args.model)
        reply = scrub(result["reply"], home=home)
        commands = [scrub(command, home=home) for command in result["commands"]]
        assertions = []
        for assertion in probe["assertions"]:
            passed, seen = evaluate(assertion, haystack_for(assertion, reply=reply, commands=commands, graph=graph))
            assertions.append(
                {
                    "name": assertion["name"],
                    "over": assertion.get("over", "reply"),
                    "kind": assertion["kind"],
                    "values": assertion["values"],
                    "outcome": "pass" if passed else "fail",
                    "seen": seen,
                }
            )
            if not passed:
                outcome = "fail"
        runs.append({"prompt": probe["prompt"], "reply": reply, "commands": commands, "assertions": assertions})

        if args.keep:
            print(f"sandbox kept at {root}", file=sys.stderr)
        else:
            shutil.rmtree(root, ignore_errors=True)

    evidence = {
        "schema_version": SCHEMA_VERSION,
        "kit": args.kit,
        "files": [
            {
                "path": path.relative_to(REPO_ROOT).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in files
        ],
        "recorded": {
            "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "by": git_identity(),
            "opencode_version": opencode_version(opencode),
            "model": args.model or "opencode default",
            "platform": sys.platform,
        },
        "runs": runs,
        "outcome": outcome,
    }

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    destination = EVIDENCE_DIR / f"{args.kit}.json"
    # Canonical JSON: sorted keys, two-space indent, LF, trailing newline. That is
    # already the fixed point of every formatting hook in this repository, so a
    # recording is not silently edited after it was recorded.
    destination.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {destination.relative_to(REPO_ROOT).as_posix()}: {outcome}", file=sys.stderr)

    return 0 if outcome == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
