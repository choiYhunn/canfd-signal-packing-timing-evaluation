"""Recompute the README headline numbers from the published summary tables.

This checks that every number quoted in README.md / final_campaign/README.md follows from
the CSV files in this repository. It does not regenerate those tables: that needs the
private raw TRC captures. Standard library only.

Usage: python tools/verify_headline_numbers.py      (exit code 1 on any mismatch)
"""
import csv
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FINAL = ROOT / 'final_campaign' / 'analysis'
failures = []


def rows(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def check(label, value, expected, tol):
    ok = abs(value - expected) <= tol
    print(f"{'ok  ' if ok else 'FAIL'} {label}: {value:.3f} (README {expected})")
    if not ok:
        failures.append(label)


# 1. Initial 2-node campaign (n=10 per condition, same-node background).
two = {(r['strategy'], r['load_pct_label']): float(r['mean'])
       for r in rows(ROOT / 'analysis' / 'summary_tables' / 'condition_summary.csv')
       if r['metric'] == 'jitter_std_us'}
check('2-node A60 jitter', two[('A', '60')], 59.764, 0.001)
check('2-node C60 jitter', two[('C', '60')], 22.098, 0.001)
check('2-node A60-C60', two[('A', '60')] - two[('C', '60')], 37.667, 0.001)

# 2. 3-node repeated campaign (n=5, external background node).
n5 = {r['condition']: r for r in rows(FINAL / 'n5' / 'condition_summary_n5.csv')}
for cond, mean, gap in (('A60', 30.22, 240), ('B60', 61.61, 235), ('C60', 24.78, 238)):
    check(f'3-node {cond} jitter mean', float(n5[cond]['jitter_mean']), mean, 0.005)
    check(f'3-node {cond} nominal gap us', float(n5[cond]['dummy_gap_nominal_us']), gap, 0)
check('3-node B60-C60', float(n5['B60']['jitter_mean']) - float(n5['C60']['jitter_mean']), 36.83, 0.005)

# 3. Strategy A only, gap confirmation (n=3, independent reset, permuted order).
confirm = {r['configured_gap_us']: r for r in rows(FINAL / 'gap_sweep' / 'confirm' / 'gap_jitter_n3_summary.csv')}
for gap, mean in (('238', 26.37), ('240', 56.84), ('244', 75.96), ('250', 21.83)):
    check(f'A gap {gap} us jitter (n=3)', float(confirm[gap]['mean']), mean, 0.005)

# 4. Full 230-250 us sweep (n=1 per point, exploratory).
sweep_dir = FINAL / 'gap_sweep' / 'response_full'
jit = {(r['strategy'], r['configured_gap_us']): float(r['jitter_us']) for r in rows(sweep_dir / 'gap_response_metrics.csv')}
occ = {(r['strategy'], r['configured_gap_us']): float(r['reconstructed_total_occ_pct']) for r in rows(sweep_dir / 'occupancy_metrics.csv')}
check('sweep A 238 us jitter', jit[('A', '238')], 25.49, 0.005)
check('sweep A 242 us jitter', jit[('A', '242')], 73.57, 0.005)
check('sweep A 238->242 occupancy change pp', occ[('A', '242')] - occ[('A', '238')], -0.95, 0.005)
check('sweep C 238 us jitter', jit[('C', '238')], 26.58, 0.005)
check('sweep C 242 us jitter', jit[('C', '242')], 73.89, 0.005)

# 5. No measured PCAN bus load was stored in any campaign table.
for path, cols in ((ROOT / 'analysis' / 'summary_tables' / 'run_level_metrics.csv', ['pcan_actual_mean_load_pct']),
                   (FINAL / 'n5' / 'run_level_metrics.csv', ['actual_pcan_mean_load']),
                   (FINAL / 'pilot_run1' / 'run_manifest.csv', ['actual_pcan_mean_load'])):
    filled = sum(1 for r in rows(path) for c in cols if r[c].strip())
    ok = filled == 0
    print(f"{'ok  ' if ok else 'FAIL'} measured PCAN load empty in {path.relative_to(ROOT).as_posix()}: {filled} filled")
    if not ok:
        failures.append(str(path))

print('\nall headline numbers reproduced' if not failures else f'\n{len(failures)} mismatch(es)')
sys.exit(1 if failures else 0)
