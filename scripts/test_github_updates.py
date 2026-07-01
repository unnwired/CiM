#!/usr/bin/env python3
"""Smoke tests for GitHub update helpers."""
from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

import github_updates as gh  # noqa: E402


def test_version_from_release():
    assert gh.version_from_release("v1.0.4", "CiM-Update-1.0.4.zip") == "1.0.4"
    assert gh.version_from_release("1.0.5", "") == "1.0.5"
    assert gh.is_newer_version("1.0.4", "1.0.3")
    assert not gh.is_newer_version("1.0.3", "1.0.4")
    print("version_from_release OK")


def test_pick_release_asset():
    release = {
        "tag_name": "v1.0.4",
        "assets": [
            {"name": "README.txt", "browser_download_url": "https://example.com/r.txt"},
            {"name": "CiM-Update-1.0.4.zip", "browser_download_url": "https://example.com/u.zip"},
        ],
    }
    asset = gh.pick_release_asset(release)
    assert asset is not None
    assert asset["name"] == "CiM-Update-1.0.4.zip"
    print("pick_release_asset OK")


def test_extract_layout():
    with tempfile.TemporaryDirectory() as tmp:
        install = Path(tmp) / "CiM"
        install.mkdir()
        gh.configure_paths(install)

        staging = Path(tempfile.mkdtemp())
        inner = staging / "CiM-Update-9.9.9"
        inner.mkdir()
        (inner / "update.manifest.json").write_text(
            json.dumps({"version": "9.9.9", "files": []}), encoding="utf-8"
        )
        (inner / "payload").mkdir()
        (inner / "payload" / "start_cim.bat").write_text("@echo off", encoding="utf-8")

        zip_path = staging / "pkg.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for p in inner.rglob("*"):
                if p.is_file():
                    zf.write(p, p.relative_to(staging).as_posix())

        # Simulate download by extracting via internal helper
        extract_tmp = staging / "_extract"
        extract_tmp.mkdir()
        target = gh._update_dir() / "CiM-Update-9.9.9"
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_tmp)
        gh._normalize_extracted_root(extract_tmp, target)

        assert (target / "update.manifest.json").is_file()
        assert (target / "payload" / "start_cim.bat").is_file()
        print("extract_layout OK")


def test_manifest_utf8_bom():
    with tempfile.TemporaryDirectory() as tmp:
        install = Path(tmp) / "CiM"
        (install / "UPDATE" / "CiM-Update-1.0.5").mkdir(parents=True)
        pkg = install / "UPDATE" / "CiM-Update-1.0.5"
        (pkg / "payload").mkdir()
        (pkg / "payload" / "version.txt").write_text("1.0.5", encoding="utf-8")
        manifest = {
            "version": "1.0.5",
            "files": [{"path": "version.txt", "sha256": "x", "size": 5}],
        }
        # PowerShell Set-Content -Encoding UTF8 writes BOM
        (pkg / "update.manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8-sig"
        )
        sys.path.insert(0, str(ROOT / "server"))
        import importlib
        ua = importlib.import_module("update_apply")
        ua.configure_install_root(install)
        (install / "version.txt").write_text("1.0.4", encoding="utf-8")
        info = ua._check_local_package(pkg, "1.0.4", validate_files=True)
        assert info is not None
        assert info["version"] == "1.0.5"
        print("manifest_utf8_bom OK")


def test_version_bom_no_false_github_offer():
    """BOM-prefixed 1.0.5 must not be treated as older than GitHub 1.0.4."""
    assert not gh.is_newer_version("1.0.4", "1.0.5")
    assert not gh.is_newer_version("1.0.4", "\ufeff1.0.5")
    assert gh.parse_version_tuple("\ufeff1.0.5") == (1, 0, 5)
    assert gh.parse_version_tuple("1.0.5") == (1, 0, 5)
    print("version_bom_no_false_github_offer OK")


def test_https_ssl_context_uses_certifi():
    from http_ssl import https_ssl_context

    import certifi

    ctx = https_ssl_context()
    assert ctx is not None
    assert Path(certifi.where()).is_file()
    print("https_ssl_context_uses_certifi OK")


def test_github_api_ssl_smoke():
    """Live check — fails fast if certifi/SSL cannot reach GitHub API."""
    try:
        release = gh.fetch_latest_release()
    except RuntimeError as e:
        if "CERTIFICATE_VERIFY_FAILED" in str(e):
            raise AssertionError(f"GitHub SSL still broken: {e}") from e
        raise
    print(f"github_api_ssl_smoke OK (release={'found' if release else 'none'})")


def test_read_version_utf8_bom_file():
    import importlib

    with tempfile.TemporaryDirectory() as tmp:
        install = Path(tmp) / "CiM"
        install.mkdir()
        (install / "version.txt").write_bytes(b"\xef\xbb\xbf1.0.5")
        ua = importlib.import_module("update_apply")
        ua.configure_install_root(install)
        assert ua._read_version() == "1.0.5"
        assert not gh.is_newer_version("1.0.4", ua._read_version())
    print("read_version_utf8_bom_file OK")


if __name__ == "__main__":
    test_version_from_release()
    test_pick_release_asset()
    test_extract_layout()
    test_manifest_utf8_bom()
    test_version_bom_no_false_github_offer()
    test_https_ssl_context_uses_certifi()
    test_github_api_ssl_smoke()
    test_read_version_utf8_bom_file()
    print("ALL PASS")
