# GitHub Private Push Report

Report date: 2026-07-22 (Asia/Seoul)

## Repository

- URL: https://github.com/choiYhunn/canfd-signal-packing-timing-evaluation
- Visibility: **PRIVATE**
- Default branch: `main`
- Remote: `origin` (`https://github.com/choiYhunn/canfd-signal-packing-timing-evaluation.git`)
- Description: Hardware E2E evaluation of CAN-FD signal-packing strategies using RA6M5, PCAN traces, and oscilloscope timing markers.
- GitHub-added README, `.gitignore`, or license: none; the remote was created from the reviewed local source only

## Push and commit verification

- Initial release-candidate commit: `cf80ffaf52191f334417d79c01bb00ccaf4b5ddf`
- Audited content commit at first push: `40c781b0487340bd3facb10c3db92a8b60e536a8`
- Local `main` and remote `origin/main` were both `40c781b0487340bd3facb10c3db92a8b60e536a8` immediately after repository creation
- This report, the final readiness update, and the updated file manifest are committed and pushed afterward; final local/remote equality is verified after that commit
- Commit amendment: not performed; the original author and committer already matched

## Author metadata and authentication

- Repository-local Git identity: `choiYhunn <yhchoihoon@gmail.com>`
- Existing and new commit author/committer: `choiYhunn <yhchoihoon@gmail.com>`
- Global Git configuration: not modified
- GitHub CLI: 2.96.0
- GitHub authentication: account `choiYhunn`, Git protocol HTTPS, credentials stored in the operating-system keyring
- No access token, device code, or authentication secret is stored in this repository or report

## Files and size

- Original reviewed candidate: 55 tracked files
- First push after adding `PRE_PUSH_AUDIT.md` and `PUBLIC_RELEASE_PENDING.md`: 57 remote blobs
- Final set after adding this required report: 58 tracked files
- First-push remote blob payload: 2,092,907 bytes (1.996 MiB); final payload is rechecked after the report commit
- Files at least 10 MiB: 0
- Files over GitHub's 100 MiB limit: 0
- Git LFS objects: 0
- Symbolic links: 0
- Submodules: 0

The increase from the 55-file audited baseline consists only of the three required governance records: `PRE_PUSH_AUDIT.md`, `PUBLIC_RELEASE_PENDING.md`, and this report.

## Privacy and exclusion verification

- Final requested identifier/credential-pattern matching lines: 20, all reviewed as parser vocabulary or governance-policy self-reference
- Non-allowlisted personal-information or secret findings: 0
- Absolute Windows user paths in release content: 0
- Original 120-TRC dataset: excluded
- Original oscilloscope/Scope source data: excluded
- Final report and presentation PDFs and office documents: excluded
- ZIP/7z/RAR and private archives: excluded
- ELF/HEX/MAP/AXF/BIN and Debug/Release build outputs: excluded
- Renesas/vendor SDK trees, generated project trees, manuals, and paper PDFs: excluded
- Synthetic sample: included only as `sample_data/synthetic_example.trc` and identified as non-experimental example data

## README and remote-link verification

- `README.md` and `README_KO.md`: present on `main`
- Research question, A/B/C workload, RA6M5 implementation, fixed-payload control, TRC/Scope separation, 120/120 QC result, A60/C60 values, strict-matched occupancy, and 80% claim-gate failure: preserved
- Overclaim exclusions, including same-node dummy traffic and no motor/PID/physical-PWM validation: present
- Remote analysis figures: 14 PNG files
- Remote `sample_data` files: 3
- Local Markdown targets for the Korean README, analysis figures, summary tables, sample data, and license review: resolved

## License and public-release status

- License: **LICENSE PENDING**
- No MIT, Apache, GPL, or other license was inferred or added
- Until authorized rightsholders select a license, no reuse permission is granted and all applicable rights are reserved
- Repository visibility must remain **PRIVATE**
- Public conversion requires every approval in `PUBLIC_RELEASE_PENDING.md`; no public conversion was attempted
