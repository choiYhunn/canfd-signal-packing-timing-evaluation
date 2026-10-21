import sys, csv, os
from pathlib import Path
import numpy as np, pandas as pd
HERE=Path.cwd(); RAW=HERE.parents[0]
sys.path.insert(0,str(HERE.parents[1]/"trace_fixed2"/"analysis_n10"))
import analyze_fixed2_64b_n10 as canon
dn=csv.DictWriter(open(os.devnull,"w",newline=""),fieldnames=["source_file","strategy","load_mode","load_pct_label","run","analysis_window","timestamp_us","gap_us","error_us","abs_error_us"])
rows=[]
for r in range(1,9):
    f=f"a2_{r}.trc"; p=RAW/f
    if not p.exists(): continue
    res=canon.parse_trace(p,canon.FileKey(f,"A",2,"60",r),dn)
    fr=res["frames"]
    ts=np.array([x.timestamp_us for x in fr]); cid=np.array([x.can_id for x in fr])
    bg=np.sort(ts[(cid>=0x300)&(cid<=0x30F)])
    d=np.diff(bg); d=d[d>0]
    vals,cnts=np.unique(d,return_counts=True)
    mode=int(vals[np.argmax(cnts)])
    nbg=len(set(cid[(cid>=0x300)&(cid<=0x30F)].tolist()))
    rows.append(dict(file=f,run=r,configured_gap_us="UNKNOWN(nominal snapshot=240; not confirmable per-run from TRC)",
        observed_bg_spacing_median_us=float(np.median(d)),
        observed_bg_spacing_mode_us=mode,
        observed_bg_spacing_iqr_us=float(np.percentile(d,75)-np.percentile(d,25)),
        observed_bg_spacing_p10_us=float(np.percentile(d,10)),
        observed_bg_spacing_p90_us=float(np.percentile(d,90)),
        n_bg_ids=nbg, n_bg_frames=len(bg)))
df=pd.DataFrame(rows)
df.to_csv("bg_gap_provenance_audit.csv",index=False,encoding="utf-8-sig",lineterminator="\n")
pd.set_option("display.width",200)
print(df[["file","run","observed_bg_spacing_median_us","observed_bg_spacing_mode_us","observed_bg_spacing_iqr_us","observed_bg_spacing_p10_us","observed_bg_spacing_p90_us","n_bg_ids"]].to_string(index=False))
