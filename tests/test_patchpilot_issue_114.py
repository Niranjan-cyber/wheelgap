"""Issue #114: --online must not look up private-index lockfile packages on public PyPI."""

from __future__ import annotations

import re

from wheelgap.cli import main
from wheelgap.sources import parse_poetry_lock

# A uv.lock with a package the lock says came from a private index (registry = ...), whose only
# locked wheel is a Windows one: on a Linux target the lock alone must report a gap.
UV_LOCK = (
    'version = 1\nrequires-python = ">=3.12"\n\n'
    '[[package]]\nname = "app"\nversion = "0"\nsource = { editable = "." }\n'
    'dependencies = [{ name = "purewheel" }]\n\n'
    '[[package]]\nname = "purewheel"\nversion = "3.1"\n'
    'source = { registry = "https://pkgs.example.com/simple" }\n'
    'wheels = [{ url = "https://pkgs.example.com/purewheel-3.1-cp313-cp313-win_amd64.whl" }]\n'
)

# The same private-index package in a poetry.lock, recorded through the [package.source] table.
POETRY_LOCK = (
    '[[package]]\nname = "purewheel"\nversion = "3.1"\ndescription = ""\noptional = false\n'
    'python-versions = ">=3.9"\ngroups = ["main"]\n'
    "files = [\n"
    '    {file = "purewheel-3.1-cp313-cp313-win_amd64.whl", hash = "sha256:00"},\n'
    "]\n\n"
    "[package.source]\n"
    'type = "legacy"\n'
    'url = "https://pkgs.example.com/simple"\n'
    'reference = "private"\n\n'
    '[metadata]\nlock-version = "2.1"\npython-versions = ">=3.9"\ncontent-hash = "00"\n'
)


def run(capsys, *argv):
    code = main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_online_uv_lock_keeps_private_index_packages_off_pypi(capsys, fake_pypi, tmp_path):
    (tmp_path / "uv.lock").write_text(UV_LOCK, encoding="utf-8")
    code, out, err = run(capsys, str(tmp_path), "--online", "-p", "3.13", "-t", "linux-x86_64")
    # Nothing was fetched for the private-index package.
    assert not [url for url in fake_pypi if "purewheel" in url], fake_pypi
    # Its locked files still count: the locked wheel is a Windows one, so the package has a gap.
    assert code == 1
    assert "purewheel" in out
    # A note tells how many packages from other indexes were checked from the lock only.
    note = err + out
    assert "index" in note.lower() and re.search(r"\b1\b", note), note


def test_online_poetry_lock_keeps_private_index_packages_off_pypi(capsys, fake_pypi, tmp_path):
    (tmp_path / "poetry.lock").write_text(POETRY_LOCK, encoding="utf-8")
    code, out, err = run(capsys, str(tmp_path), "--online", "-p", "3.13", "-t", "linux-x86_64")
    assert not [url for url in fake_pypi if "purewheel" in url], fake_pypi
    assert code == 1
    assert "purewheel" in out
    note = err + out
    assert "index" in note.lower() and re.search(r"\b1\b", note), note


def test_parse_poetry_lock_records_registry(tmp_path):
    path = tmp_path / "poetry.lock"
    path.write_text(POETRY_LOCK, encoding="utf-8")
    (src,) = [parse_poetry_lock(path)]
    (pkg,) = src.packages
    assert pkg.registry == "https://pkgs.example.com/simple"


def test_without_online_a_private_package_with_no_locked_files_is_still_looked_up(fake_pypi):
    # review on #133: the filter must only apply to --online, so behaviour without it is unchanged
    from wheelgap.pypi import fill_all
    from wheelgap.sources import Package

    pkg = Package(name="purewheel", version="1.0", files=None, registry="https://pkgs.example.com/simple")
    assert fill_all([pkg]) == 0
    assert [url for url in fake_pypi if "purewheel" in url], fake_pypi


def test_only_the_exact_pypi_simple_index_counts_as_pypi():
    # review on #133: the same rule recheck_lock() used before
    from wheelgap.pypi import is_pypi

    assert is_pypi(None) and is_pypi("https://pypi.org/simple") and is_pypi("https://pypi.org/simple/")
    assert not is_pypi("https://pkgs.example.com/simple") and not is_pypi("https://pypi.python.org/simple")
