#!/usr/bin/env python3

import argparse
import re
import subprocess
import sys
from pathlib import Path

VERSION_PATTERN = re.compile(
    r'(?m)^(version\s*=\s*")(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(")$'
)
PRE_RELEASE_COMMANDS = (
    ("-m", "ruff", "check", "src/wikimore", "scripts"),
    ("-m", "ruff", "format", "--check", "src/wikimore", "scripts"),
    ("-m", "djlint", "src/wikimore", "--check"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Bump the project version in pyproject.toml and create a release commit "
            "and tag."
        )
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--major",
        action="store_true",
        help="Bump the major version and reset minor/patch.",
    )
    group.add_argument(
        "--minor", action="store_true", help="Bump the minor version and reset patch."
    )
    group.add_argument("--patch", action="store_true", help="Bump the patch version.")
    parser.add_argument(
        "--skip-checks",
        "--skip-lint",
        dest="skip_checks",
        action="store_true",
        help="Skip the pre-release checks.",
    )
    return parser.parse_args()


def run_git(*args: str, repo_root: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def run_python(*args: str, repo_root: Path) -> None:
    subprocess.run(
        [sys.executable, *args],
        cwd=repo_root,
        check=True,
    )


def ensure_clean_worktree(repo_root: Path) -> None:
    status = run_git("status", "--short", repo_root=repo_root)
    if status:
        raise SystemExit("Working tree is not clean. Commit or stash changes first.")


def load_version(pyproject_path: Path) -> tuple[str, tuple[int, int, int]]:
    content = pyproject_path.read_text(encoding="utf-8")
    match = VERSION_PATTERN.search(content)
    if not match:
        raise SystemExit("Could not find [project] version in pyproject.toml.")
    version = (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
    )
    return content, version


def bump_version(
    version: tuple[int, int, int], args: argparse.Namespace
) -> tuple[int, int, int]:
    major, minor, patch = version
    if args.major:
        return major + 1, 0, 0
    if args.minor:
        return major, minor + 1, 0
    return major, minor, patch + 1


def write_version(
    pyproject_path: Path, content: str, new_version: tuple[int, int, int]
) -> str:
    version_text = ".".join(str(part) for part in new_version)
    updated = VERSION_PATTERN.sub(rf"\g<1>{version_text}\g<5>", content, count=1)
    pyproject_path.write_text(updated, encoding="utf-8")
    return version_text


def ensure_tag_does_not_exist(repo_root: Path, tag_name: str) -> None:
    if run_git("tag", "--list", tag_name, repo_root=repo_root):
        raise SystemExit(f"Tag {tag_name} already exists.")


def ensure_pre_release_checks_pass(repo_root: Path) -> None:
    for command in PRE_RELEASE_COMMANDS:
        try:
            run_python(*command, repo_root=repo_root)
        except subprocess.CalledProcessError as exc:
            raise SystemExit(
                "Pre-release checks failed. Fix the errors or re-run with --skip-checks."
            ) from exc


def create_release_commit(repo_root: Path, tag_name: str) -> None:
    run_git("add", "pyproject.toml", repo_root=repo_root)
    run_git("commit", "-m", f"Release {tag_name}", repo_root=repo_root)


def create_tag(repo_root: Path, tag_name: str) -> None:
    run_git("tag", "-m", f"Release {tag_name}", tag_name, repo_root=repo_root)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    pyproject_path = repo_root / "pyproject.toml"

    ensure_clean_worktree(repo_root)
    if not args.skip_checks:
        ensure_pre_release_checks_pass(repo_root)
    content, current_version = load_version(pyproject_path)
    new_version = bump_version(current_version, args)
    version_text = ".".join(str(part) for part in new_version)
    tag_name = f"v{version_text}"
    ensure_tag_does_not_exist(repo_root, tag_name)
    write_version(pyproject_path, content, new_version)
    create_release_commit(repo_root, tag_name)
    create_tag(repo_root, tag_name)
    print(f"Released {tag_name}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        if exc.stderr:
            print(exc.stderr.strip(), file=sys.stderr)
        raise SystemExit(exc.returncode) from exc
