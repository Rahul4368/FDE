# FDE Case Study Audit — VS Code setup

This folder contains the audit script and the complete source pack. Python 3.8+ is enough; the script uses only the Python standard library.

## Open and run in VS Code (Windows)

1. Extract `fde_case_fixed.zip` to a folder, for example `C:\\Users\\rahul\\Desktop\\fde_case_fixed`.
2. In VS Code, choose **File → Open Folder** and select that extracted folder.
3. Open **Terminal → New Terminal**. Check that the terminal path ends in `fde_case_fixed`.
4. Check Python:
   ```powershell
   python --version
   ```
   If that command is not found, try `py --version` and replace `python` with `py` in the commands below.
5. Run the audit:
   ```powershell
   python analyze.py
   ```
6. Check the submission word count:
   ```powershell
   python analyze.py --words submission.md
   ```
7. Run the baseline/fix checks:
   ```powershell
   python analyze.py --check
   ```

## Why the original error happened

`analyze.py` looks for `2-call-records.md` next to itself (or in the current folder). Your original ZIP had `analyze.py` but did not include `2-call-records.md`, so the script stopped with `ERROR: 2-call-records.md not found`. This ZIP includes the missing file. Keep all four source Markdown files next to `analyze.py`.

## Expected results

- `python analyze.py` prints an audit of 20 calls and creates `out\\audit.csv` and `out\\findings.json`.
- `python analyze.py --words submission.md` reports the word count. The case brief's limit is 800 words across sections a–f.
- `python analyze.py --check` is expected to show **FAIL** on the supplied baseline because the fixes have not actually been deployed. It is a regression check, not a setup error. The script exits successfully unless `--strict` is added.

## Files

- `analyze.py` — audit, word count, and checks
- `2-call-records.md` — 20 call transcripts and tool logs
- `3-weekly-summary.md` — management's weekly summary
- `4-tool-reference.md` — tool behavior reference
- `1-brief.md` — task requirements
- `submission.md` — draft case-study submission
- `session_log.md` — transparent working/session notes
- `out/audit.csv`, `out/findings.json` — generated audit outputs
