#!/usr/bin/env python3
"""One-shot text replacements for CiM rebrand. Run from repo root."""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {
    ".git", "node_modules", "frontend/build", "runtime", "data",
    ".cursor", "agent-transcripts",
}
SKIP_FILES_SUFFIX = {".pyc", ".enc", ".db", ".csv", ".zip", ".exe", ".png", ".ico", ".jpg", ".woff", ".woff2"}

# Order matters — longer / more specific first
REPLACEMENTS = [
    ("Get-FlowXDistProfilePath", "Get-CiMDistProfilePath"),
    ("Get-FlowXPaths", "Get-CiMPaths"),
    ("flowx_bootstrap", "cim_bootstrap"),
    ("FlowXKnowledgeBase", "CiMKnowledgeBase"),
    ("AboutFlowXModalBody", "AboutCiMModalBody"),
    ("FLOWX_CHROME_INTRO_READY_EVENT", "CIM_CHROME_INTRO_READY_EVENT"),
    ("flowx-chrome-intro-ready", "cim-chrome-intro-ready"),
    ("flowx-kb-chrome-intro-seen", "cim-kb-chrome-intro-seen"),
    ("flowx-kb-sidebar-chrome--intro", "cim-kb-sidebar-chrome--intro"),
    ("flowx-kb-sidebar-chrome--open", "cim-kb-sidebar-chrome--open"),
    ("flowx-kb-sidebar-chrome", "cim-kb-sidebar-chrome"),
    ("flowx-kb-sidebar-arrow", "cim-kb-sidebar-arrow"),
    ("flowx-kb-resize-handle--active", "cim-kb-resize-handle--active"),
    ("flowx-kb-resize-handle", "cim-kb-resize-handle"),
    ("flowx-kb-close-btn", "cim-kb-close-btn"),
    ("flowx-kb-header-title", "cim-kb-header-title"),
    ("flowx-kb-header", "cim-kb-header"),
    ("flowx-kb-section-paragraph", "cim-kb-section-paragraph"),
    ("flowx-kb-section-heading", "cim-kb-section-heading"),
    ("flowx-kb-section", "cim-kb-section"),
    ("flowx-kb-body", "cim-kb-body"),
    ("flowx-kb-scrim", "cim-kb-scrim"),
    ("flowx-kb-panel--width-animate", "cim-kb-panel--width-animate"),
    ("flowx-kb-panel--closed", "cim-kb-panel--closed"),
    ("flowx-kb-panel--open", "cim-kb-panel--open"),
    ("flowx-kb-panel--slide", "cim-kb-panel--slide"),
    ("flowx-kb-panel", "cim-kb-panel"),
    ("flowx-kb-chrome-glow--down", "cim-kb-chrome-glow--down"),
    ("flowx-kb-chrome-glow--up", "cim-kb-chrome-glow--up"),
    ("flowx-kb-chrome-glow", "cim-kb-chrome-glow"),
    ("flowx-row-edit-btn", "cim-row-edit-btn"),
    ("--flowx-kb-slide-ms", "--cim-kb-slide-ms"),
    ("--flowx-kb-chrome-width", "--cim-kb-chrome-width"),
    ("flowx-drawing-", "cim-drawing-"),
    ("flowx-chart-", "cim-chart-"),
    ("flowx-kb-", "cim-kb-"),
    ("FlowX-Update-", "CiM-Update-"),
    ("FlowXSetup-", "CiMSetup-"),
    ("FlowXSetup", "CiMSetup"),
    ("FlowX.iss", "CiM.iss"),
    ("FlowXIss", "CiMIss"),
    ("start_flowx.bat", "start_cim.bat"),
    ("stop_flowx.bat", "stop_cim.bat"),
    ("export_flowx.ps1", "export_cim.ps1"),
    ("Build-FlowX", "Build-CiM"),
    ("Restore-FlowXDevBuild", "Restore-CiMDevBuild"),
    ("Repair-FlowXLicense", "Repair-CiMLicense"),
    ("Run-FlowXFullGate", "Run-CiMFullGate"),
    ("Test-FlowXPackagedSmoke", "Test-CiMPackagedSmoke"),
    ("Test-FlowXInstallE2E", "Test-CiMInstallE2E"),
    ("Test-FlowXGitHubAutoUpdate", "Test-CiMGitHubAutoUpdate"),
    ("Test-FlowXVersionBomUpdateCheck", "Test-CiMVersionBomUpdateCheck"),
    ("Verify-FlowXBuildPrerequisites", "Verify-CiMBuildPrerequisites"),
    ("Verify-FlowXLicenseChain", "Verify-CiMLicenseChain"),
    ("Generate-FlowXInstallKey", "Generate-CiMInstallKey"),
    ("Show-FlowXInstallKey", "Show-CiMInstallKey"),
    ("Diagnose-FlowXInstall", "Diagnose-CiMInstall"),
    ("FlowXApplyUpdate", "CiMApplyUpdate"),
    ("FlowXDownloadUpdate", "CiMDownloadUpdate"),
    ("FlowXInstallLocator", "CiMInstallLocator"),
    ("FlowXUpdatePackage", "CiMUpdatePackage"),
    ("Apply-FlowXLocalUpdate", "Apply-CiMLocalUpdate"),
    ("installer\\output\\FlowX", "installer\\output\\CiM"),
    ("installer/output/FlowX", "installer/output/CiM"),
    ("output\\FlowX", "output\\CiM"),
    ("output/FlowX", "output/CiM"),
    ("D:\\FlowX", "D:\\CiM"),
    ("D:/FlowX", "D:/CiM"),
    (r"Join-Path $env:LOCALAPPDATA \"FlowX\"", r"Join-Path $env:LOCALAPPDATA \"CiM\""),
    ('/"FlowX/"', '/"CiM/"'),
    ('\\"FlowX\\"', '\\"CiM\\"'),
    ("/FlowX/", "/CiM/"),
    ("\\\\FlowX\\\\", "\\\\CiM\\\\"),
    ('"FlowX"', '"CiM"'),
    ("'FlowX'", "'CiM'"),
    ("/FlowX\"", "/CiM\""),
    ("LOCALAPPDATA%\\\\FlowX", "LOCALAPPDATA%\\\\CiM"),
    ("%LOCALAPPDATA%\\FlowX", "%LOCALAPPDATA%\\CiM"),
    ("%LOCALAPPDATA%/FlowX", "%LOCALAPPDATA%/CiM"),
    ('Path(local) / "FlowX"', 'Path(local) / "CiM"'),
    ('/"FlowX" /', '/"CiM" /'),
    (".flowx-license", ".cim-license"),
    ("flowx-updates", "cim-updates"),
    ("flowx-desktop", "cim-desktop"),
    ("FlowXDesktop", "CiMDesktop"),
    ("FLOWX_LICENSE_SECRET", "CIM_LICENSE_SECRET"),
    ("FLOWX_DEV", "CIM_DEV"),
    ("FLOWX_NO_PAUSE", "CIM_NO_PAUSE"),
    ("FLOWX_URL", "CIM_URL"),
    ("FLOWX_GITHUB_OWNER", "CIM_GITHUB_OWNER"),
    ("FLOWX_GITHUB_REPO", "CIM_GITHUB_REPO"),
    ("FLOWX_SKIP_FRONTEND_BUILD", "CIM_SKIP_FRONTEND_BUILD"),
    ("FLOWX_FORCE_FRONTEND_BUILD", "CIM_FORCE_FRONTEND_BUILD"),
    ("FLOWX_DISTRIBUTION", "CIM_DISTRIBUTION"),
    ("FlowX-SupportQr-v1", "CiM-SupportQr-v1"),
    ("About FlowX", "About Charts In Motion"),
    ("FlowX Knowledge Base", "Charts In Motion Knowledge Base"),
    ("Open FlowX Knowledge Base", "Open Charts In Motion Knowledge Base"),
    ("Close FlowX Knowledge Base", "Close Charts In Motion Knowledge Base"),
    ("Edit Knowledge Base", "Edit Knowledge Base"),
    ("Support the Development", "Support the Development"),
    ("Shut down FlowX?", "Shut down Charts In Motion?"),
    ("Loading FlowX", "Loading Charts In Motion"),
    ("FlowX Bootstrap", "Charts In Motion Bootstrap"),
    ("FlowX Backend", "CiM Backend"),
    ("FlowX update", "Charts In Motion update"),
    ("FlowX will close", "Charts In Motion will close"),
    ("No FlowX update", "No Charts In Motion update"),
    ("Apply FlowX update", "Apply Charts In Motion update"),
    ("Applying update — FlowX is closing", "Applying update — Charts In Motion is closing"),
    ("Product: FlowX", "Product: Charts In Motion"),
    ("FlowX folder", "Charts In Motion folder"),
    ("FlowX\\UPDATE", "CiM\\UPDATE"),
    ("FlowX/UPDATE", "CiM/UPDATE"),
    ("FlowX.lnk", "Charts In Motion.lnk"),
    ("unnwired/flowx-updates", "unnwired/cim-updates"),
    ("flowx-e2e-install.log", "cim-e2e-install.log"),
    ("flowx-gate-install.log", "cim-gate-install.log"),
    ("Stop-FlowXProcesses", "Stop-CiMProcesses"),
    ("========== FlowX full gate", "========== CiM full gate"),
    ("=== FlowX install E2E", "=== CiM install E2E"),
    ('"FlowX Dev"', '"Charts In Motion Dev"'),
    ("'FlowX Dev'", "'Charts In Motion Dev'"),
    ("FlowX Dev", "Charts In Motion Dev"),
    ("FlowX license", "Charts In Motion license"),
    ("reinstall FlowXSetup", "reinstall CiMSetup"),
    ("FlowX could not decrypt", "Charts In Motion could not decrypt"),
    ("FlowX-Update ZIP", "CiM-Update ZIP"),
    ("from FlowX folder", "from the Charts In Motion folder"),
    ("second FlowX window", "second Charts In Motion window"),
    ("No active FlowX window", "No active Charts In Motion window"),
    ("FlowX is", "Charts In Motion is"),
    ("FlowX's", "Charts In Motion's"),
    ("FlowX ", "Charts In Motion "),
    ("FlowX.", "Charts In Motion."),
    ("FlowX,", "Charts In Motion,"),
    ("FlowX:", "Charts In Motion:"),
    ("FlowX\"", "Charts In Motion\""),
    ("FlowX\n", "Charts In Motion\n"),
    ("# FlowX", "# Charts In Motion (CiM)"),
    ("flowx-gate", "cim-gate"),
    ("flowx-e2e", "cim-e2e"),
    ("handleApplyFlowXUpdate", "handleApplyCiMUpdate"),
    ("onApplyFlowXUpdate", "onApplyCiMUpdate"),
    ("runFlowXUpdateApply", "runCiMUpdateApply"),
    ("flowxUpdateBusy", "cimUpdateBusy"),
    ("setFlowxUpdateBusy", "setCimUpdateBusy"),
]

TEXT_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".md", ".txt", ".bat", ".ps1",
    ".html", ".css", ".iss", ".pas", ".yml", ".yaml", ".toml", ".ini", ".cfg",
    ".example", ".gitignore", ".cursorignore",
}


def should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if parts & SKIP_DIRS:
        return True
    if path.suffix.lower() in SKIP_FILES_SUFFIX:
        return True
    if "installer" in parts and "output" in parts:
        return True
    if path.name == "_rebrand_apply_text.py":
        return True
    return False


def main() -> None:
    changed = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            path = Path(dirpath) / fn
            if should_skip(path):
                continue
            if path.suffix.lower() not in TEXT_EXTENSIONS and path.name not in (
                ".gitignore", "LICENSE", "Makefile",
            ):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            orig = text
            for old, new in REPLACEMENTS:
                if old == new:
                    continue
                text = text.replace(old, new)
            if text != orig:
                path.write_text(text, encoding="utf-8", newline="\n")
                changed += 1
                print(path.relative_to(ROOT))
    print(f"Updated {changed} files")


if __name__ == "__main__":
    main()
