# Charts In Motion — User Requirements & Agent Workflow

**Purpose:** This is the product owner's contract with any AI agent or engineer working on Charts In Motion. It defines what **done** means, what must be verified before handoff, and what is **unacceptable**. Technical architecture lives in `PROJECT_HANDOFF.md`; this file defines **expectations and accountability**.

**Project root:** `D:\Programs\NSE Pulse\Claude Ai`  
**Last updated:** 08 Jun 26 (owner mandate, verification bar, accountability)

---

## 0. Owner mandate (read first)

Charts In Motion is a **shipped Windows desktop product**. The owner is **not** a QA lab. The owner is **not** responsible for catching broken builds, blank Electron shells, or failed GitHub updates that an agent marked "ready" without proof.

**An agent's job is to deliver error-free, tested code and release-ready artifacts.** If the agent cannot run the build and smoke gate locally, the agent must say so explicitly — and must **not** claim the work is complete.

**Fixing one issue must not break five things that worked before.** If a change touches distribution, encrypt, bootstrap, licensing, or updates, the agent must re-run the **full packaged pipeline** — not only unit tests or a dev-server check.

**Do not dismiss failures as "random regression" and move on.** If a release breaks after an agent's change, that is a **verification failure by the agent**, not bad luck. Name the miss, fix it, and re-verify before handoff.

---

## 1. What Charts In Motion is (one paragraph)

Charts In Motion is a local **Electron + FastAPI + React + SQLite** market-analysis app for NSE equities and indices. Clients install under e.g. `C:\FlowX` or `D:\CiM`, activate with an offline **machine code + install key**, and receive updates via **`{install}\UPDATE\CiM-Update-{version}\`** or GitHub Releases (`unnwired/cim-updates`). User data (`data\*.json`, `nse_data.db`, license) must survive updates.

---

## 2. What the product owner requires from any agent

When the owner gives instructions (feature, bug fix, release):

| Requirement | Detail |
|-------------|--------|
| **Understand intent** | Fix the real problem (e.g. chart gap vs "vanished" data), not only the symptom. |
| **Minimal correct diff** | Match existing code style; do not refactor unrelated areas. |
| **Verify the entire path yourself** | Unit tests **plus** packaged smoke **plus** full build when distribution code changed. |
| **Error-free handoff** | Do not say "done" while the build is red, smoke fails, or a known hang remains. |
| **Accountability** | If something breaks after your change, own it — fix and re-verify; do not minimize or walk away. |
| **Never ship blind** | Do not call a build "ready" without `Test-CiMPackagedSmoke.ps1` **PASS** on the export tree. |
| **No surprise Git ops** | Do not `git commit`, `git push`, or publish to GitHub unless explicitly asked. |
| **Plain-language report** | What broke, why, what changed, exact artifact paths, what the owner does on client PCs. |
| **Evidence in the reply** | Paste smoke PASS output (or full build log tail). "Should work" is not acceptable. |

### 2.1 Non‑negotiable proof the app works

A `/api/health` 200 response is **not** proof the app works. **All** of the following must pass on the **packaged export tree** (`installer\output\CiM`):

| Check | Pass criteria |
|-------|----------------|
| Backend | `GET /api/health` → 2xx |
| SPA shell | `GET /` contains `id="root"` |
| **JS bundle** | `GET /static/js/main.*.js` is JavaScript, **not** `<!DOCTYPE html>` (blank Electron shell) |
| Data | `GET /api/stocks?pageSize=500` → `total` ≥ 100 (expect ~2251) |

### 2.2 Unacceptable outcomes (do not repeat)

These have already happened and must **not** happen again:

| Outcome | Why unacceptable |
|---------|------------------|
| Blank Electron after update | Client sees empty app; owner loses trust in every release |
| Build marked ready while smoke **FAIL** | Owner wastes hours on broken ZIPs |
| GitHub update breaks license or data | Support burden; clients cannot start Charts In Motion |
| "Fixed" in repo but export not rebuilt | Client runs old encrypted tree — fix never lands |
| Long admin jobs stuck forever (e.g. Earnings+ at 46%) | Owner thinks app hung; must timeout and finish or fail clearly |
| Agent says "random regression" and stops | Preventable verification gaps are the agent's responsibility |

---

## 3. Verification bar (mandatory before handoff)

An agent **must** complete every row that applies to the change. Skip none that apply.

| Step | When required | Command / action |
|------|---------------|------------------|
| Unit tests | Always for touched Python | `python -m unittest discover -s server/tests -p "test_*.py" -v` |
| Compile check | Server / worker changes | `python -m py_compile server\server.py server\cim_bootstrap.py …` |
| Version bump | Any client-facing build | Sync `version.txt` and `installer\output\version.txt` |
| **Full build** | Encrypt, bootstrap, installer, update, server, frontend build | `.\Build-CiM.ps1` — **exit code 0** |
| **Release gate** | **Always** before "ready" | `.\scripts\Test-CiMPackagedSmoke.ps1 -InstallRoot "installer\output\CiM"` — **PASS** |
| **CIM_DEV=1 path** | **Always** (owner machine has user env `CIM_DEV=1`) | Smoke must pass with `CIM_DEV=1` set **or** script must clear it for packaged test; distribution tree must **never** skip decrypt because of dev env |
| Stronger gate | Major release / install flow changes | `.\scripts\Run-CiMFullGate.ps1` |
| Owner-facing docs | Meaningful release | Update `CHANGELOG.md`, handoff files in place |

**Rule:** If `Build-CiM.ps1` or smoke fails, the agent fixes the failure and re-runs until **PASS** — then reports to the owner. Do not hand off a red build.

### 3.1 Owner machine context (do not ignore)

- User environment variable **`CIM_DEV=1`** may be set (from `Restore-CiMDevBuild.ps1`). Packaged smoke and distribution bootstrap must still work. Encrypted export trees with `config\.fx-dist.cfg` are **never** dev trees, regardless of `CIM_DEV`.
- Dev repo checks alone are **insufficient** for anything touching encrypt, `cim_bootstrap`, updates, or licensing.

---

## 4. End‑to‑end workflow (instruction → release-ready)

```
┌─────────────────┐
│ Owner instructs │  feature / bug / release
└────────┬────────┘
         ▼
┌─────────────────┐
│ Implement fix   │  repo source; respect product rules (§7)
└────────┬────────┘
         ▼
┌─────────────────┐
│ Dev verification│  unit tests; local checks only for quick UI
└────────┬────────┘
         ▼
┌─────────────────┐
│ Bump version    │  version.txt + installer\output\version.txt
└────────┬────────┘
         ▼
┌─────────────────┐
│ Full build      │  .\Build-CiM.ps1  (step 6/6 = release gate)
└────────┬────────┘
         ▼
┌─────────────────┐
│ Release gate    │  Test-CiMPackagedSmoke.ps1 — MUST PASS
└────────┬────────┘
         ▼
┌─────────────────┐
│ Report to owner │  PASS output, paths, release notes, client steps
└────────┬────────┘
         ▼
┌─────────────────┐
│ Owner publishes │  GitHub ZIP — only when owner is satisfied
└─────────────────┘
```

### 4.1 Full distribution build

```powershell
.\Build-CiM.ps1
# or:
.\scripts\build_distribution_full.ps1 -Version "1.0.7"
```

Pipeline (`scripts\build_distribution_full.ps1`):

1. Prerequisites check  
2. `export_cim.ps1 -Mode distribution -HardenAll`  
3. `Sync-ExportDistributionFixes.ps1`  
4. `encrypt_app_code.ps1` — strip plaintext server `*.py` after encrypt (except bootstrap modules)  
5. `build_installer.ps1` → `CiMSetup-{version}.exe`  
6. `build_update_package.ps1` → `CiM-Update-{version}\` + `.zip`  
7. **`Test-CiMPackagedSmoke.ps1`** — **build fails if this fails**

License secret: `config\.build_license_secret` (gitignored) or `CIM_LICENSE_SECRET` env var. **One stable production secret** — rotating it breaks all client keys until repair.

### 4.2 Release gate (mandatory)

```powershell
.\scripts\Test-CiMPackagedSmoke.ps1 -InstallRoot "installer\output\CiM"
```

Logs on failure: `installer\output\CiM\runtime\logs\release-gate-smoke.err.log`

### 4.3 What the owner receives ("final files")

Agent delivers; owner publishes (unless owner explicitly asks agent to publish):

| Artifact | Path |
|----------|------|
| Client update folder | `installer\output\CiM-Update-{version}\` |
| GitHub upload ZIP | `installer\output\CiM-Update-{version}.zip` |
| Full installer (new machines) | `installer\output\CiMSetup-{version}.exe` |
| Build log | `runtime\logs\build-distribution.log` |
| Smoke proof | Paste `PACKAGED SMOKE PASS` block from agent run |

**Owner publishes:** [unnwired/cim-updates Releases](https://github.com/unnwired/cim-updates), tag `v{version}`, asset `CiM-Update-{version}.zip`.

**Client update:** `{install}\UPDATE\CiM-Update-{version}\` → `Install-Client-Update.bat` → restart Charts In Motion. License auto-repairs on apply (1.0.6+). If stuck: `Repair-CiMLicense-Auto.bat`.

### 4.4 Documentation sync

After meaningful releases, update in place:

- `CHANGELOG.md`
- `PROJECT_HANDOFF.md` / `PROJECT_HANDOFF_EXEC_SUMMARY.md`

Provide release title + GitHub description draft.

---

## 5. Definition of done (agent checklist)

**Do not tell the owner the work is complete until every applicable box is checked.**

- [ ] Root cause understood and fixed (not a band-aid).
- [ ] No regressions in areas that worked before (or regressions found and fixed in same pass).
- [ ] Unit/regression tests added or run for the touched area.
- [ ] `version.txt` and `installer\output\version.txt` bumped (if client build).
- [ ] `Build-CiM.ps1` completed **without error**.
- [ ] `Test-CiMPackagedSmoke.ps1` **PASS** — output pasted in reply.
- [ ] Verified under owner-like conditions (`CIM_DEV=1` does not break packaged bootstrap).
- [ ] Export has **no** plaintext `server\server.py` alongside `server.pyc.enc`.
- [ ] New root modules (e.g. `nse_index_history.py`) included in export if workers reference them.
- [ ] Long-running jobs fail or complete within bounded time — no infinite hang at one symbol/percent.
- [ ] Release notes draft + exact artifact paths provided.
- [ ] No `git commit` / `git push` / GitHub publish unless owner requested.

**If any box fails:** fix and re-run. **Do not** mark done.

---

## 6. Agent response format (when claiming "ready")

Every "ready for you to publish" message must include:

1. **What changed** (1–3 sentences, plain language)  
2. **Root cause** (if bug fix)  
3. **Tests run** (commands + pass/fail)  
4. **Smoke gate output** (the `PACKAGED SMOKE PASS` lines or explain failure + fix)  
5. **Version number**  
6. **Artifact paths** (ZIP, installer, folder)  
7. **Client steps** (if update-related)  
8. **Known risks** (honest — do not hide)

Missing evidence = not ready.

---

## 7. Product rules agents must not break

### 7.1 INR display (UI)

- Monetary values: `formatMarketCap` / `formatINR` → `₹12.34B`, `₹500.00M`, `₹1.20T`.
- BSE quarterly (crores in DB): `formatINRFromCrores()`.
- Share counts: `formatCompactCount()` — no Cr/L in labels.
- **Never** show Cr, Crore, L, Lakh in user-facing UI.

Source: `.cursor/rules/inr-display-mbt.mdc`, `frontend/src/utils/formatMarketCap.js`.

### 7.2 Client data & licensing

- Never commit `data\nse_data.db`, `runtime\`, `node_modules\`, or `installer\output\` to source repo.
- Never overwrite client watchlists, portfolio, layout, or license from update payload.
- Never ship `data\.cim-license` inside update ZIPs.
- Install keys must match `config\.fx-dist.cfg` on the **installed** tree.

### 7.3 Distribution invariants

- Code may run from `%LOCALAPPDATA%\CiM\app-cache\{version}`; **data, scripts, UPDATE** resolve from install root.
- Updates live under **`{install}\UPDATE\`**, not the install root.
- Encrypted builds: bootstrap is `server.cim_bootstrap:app`, not plain `server.server:app`.

### 7.4 Background / admin jobs

- Jobs must update progress or finish within a **bounded time**.
- If external APIs stall (Screener.in, NSE, Yahoo), job must **timeout**, report partial progress, and release the UI — not hang at one symbol for 10+ minutes.
- Swallowing errors silently (`except: pass`) without finishing the job is not acceptable for owner-visible workflows.

---

## 8. Known failure modes (next agent must know)

| Symptom | Likely cause | Agent action |
|---------|--------------|--------------|
| Blank Electron, health OK | `/static/js/*.js` returns HTML | Smoke test; encrypt stripped `server.py`; static mount / app-cache |
| `No module named 'server.server'` on smoke | Dev env or missing decrypt path | Check `CIM_DEV`; distribution profile + encrypted tree; re-run smoke |
| Build fails at step 6/6 | Smoke gate | Read `release-gate-smoke.err.log`; fix; rebuild |
| License invalid after update | Vendor profile refreshed | Auto-repair in apply (1.0.6+); else `Repair-CiMLicense-Auto.bat` |
| Earnings+ stuck at N% | Screener stall, no job timeout | Ensure stall timeout; reduce parallel hammering if needed |
| Chart vertical spike | Missing `index_history` rows | `sync_nse_index_history()`, 85-day NSE windows |
| Defence chart starts Nov 2024 | Index launch date — not a bug | Explain vs continuous symbols |
| Git push fails (huge files) | DB/binary in history | `.gitignore`; never commit `nse_data.db` |

---

## 9. Future owner requirements (not yet implemented)

Document for continuity — **do not claim done until built and smoke-tested:**

| Requirement | Intent |
|-------------|--------|
| **Per-machine feature entitlements** | Same update ZIP for all clients; features disabled per machine code via signed config inside the update (not a separate support file). |
| **Code-signed installer** | Reduce Windows SmartScreen warnings before wide rollout. |

---

## 10. How the owner works with agents

1. **Describe the goal** — user-visible outcome ("Defence chart missing months", not "fix line 500").
2. **Agent implements and self-tests** — full verification bar (§3) for anything touching server, frontend build, encrypt, bootstrap, updates, or licensing.
3. **Agent reports with evidence** — smoke PASS, paths, client steps (§6).
4. **Owner validates on a real install** when they choose — especially after past broken releases.
5. **Owner publishes** GitHub release when satisfied.

If the owner says **"release"**, they mean **release-ready files + verified gate + evidence** — not "push to GitHub for me" unless they say that explicitly.

---

## 11. Related documents

| File | Audience |
|------|----------|
| **USER_REQUIREMENTS.md** (this file) | Product owner contract — **read before any work** |
| `PROJECT_HANDOFF.md` | Technical deep-dive |
| `PROJECT_HANDOFF_EXEC_SUMMARY.md` | Short status & risks |
| `CHANGELOG.md` | Shipped changes by date |
| `docs/UPDATE.md`, `docs/CLIENT_UPDATE.md` | Client/vendor update runbooks |

---

## 12. One-line summary for any agent (Cursor, ChatGPT, or engineer)

> Implement the owner's instruction, run **Build-CiM.ps1** and **Test-CiMPackagedSmoke.ps1** until **PASS**, bump version, hand over **CiM-Update-{version}.zip** with **proof** and release notes — **never** mark a client update ready without the JS + data smoke gate, **never** treat the owner as QA, and **never** hand off error-prone code without running the full verification bar yourself.
