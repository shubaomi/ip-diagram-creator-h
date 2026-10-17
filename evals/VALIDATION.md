# Phase 1 validation: 2026-10-16

Version: 0.3.0. Scope: record contracts, package integrity and retention of the existing PPT workflow.

| Check | Evidence | Result |
| --- | --- | --- |
| Offline regression | `python -m unittest discover -s tests -v` | 25 tests passed on Windows / Python 3.13 |
| Skill metadata | System skill-creator `quick_validate.py`, run with `python -X utf8` | Passed; UTF-8 flag avoids Windows legacy code-page decoding |
| Interrupted-batch fixture | `evals/prepare_fixture.py`, then `scripts/records.py` | 03/04 to generate; 02 reconcile; 01 review; no user approvals inferred |
| Baseline cases | `evals/evals.json` | 9 definitions retained, including the existing PPT case |
| Phase-1 behavior cases | `evals/phase1.json` | 6 definitions with fixture inputs and observable expectations |
| Model A/B replay | Old/new skills on identical requests | NOT RUN; no measured model-quality improvement claimed |
| Real image generation | User-authorized identity assets | NOT RUN; no image calls or new generation charges |
| Subjective likeness / visual acceptance | User review of real outputs | NOT RUN; cannot be inferred from tests |
| New-chat skill discovery | Fresh host conversation | NOT RUN; file synchronization is not proof of host discovery |

The fixture uses a copied public sample and conspicuously synthetic approval evidence. It is not a record of actual image generation, user identity, or user acceptance. Tests check failures as well as successful paths; they do not certify that a model obeys a prompt.

Package hashes and installed-copy differences are checked with `scripts/sync_skill.py`. Rebuild the manifest after intentional source edits and recheck installations after synchronization; a past report is not a substitute for those current checks.
