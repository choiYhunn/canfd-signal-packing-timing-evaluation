# 최종 캠페인 — 3-node 외부 배경 트래픽 재실험

[루트 README(초기 캠페인)](../README.md) · [English](#english-summary)

> [!IMPORTANT]
> 이 폴더는 저장소 루트의 **초기(2-node) 캠페인** 이후에 수행한 **최종(3-node) 재실험**의 공개 가능한 source·분석 산출물입니다.
> 초기 캠페인에서는 같은 TX 노드가 부하용 dummy frame도 함께 보냈기 때문에, 전략 간에 관측된 큰 수신 지터 차이를 패킹 효과로 단정하기 어려웠습니다.
> 그래서 독립 **Background TX 노드**를 둔 3-node 구성으로 다시 측정했고, 부하를 맞추는 과정에서 **배경 트래픽 생성 간격(gap)이 함께 변하면서 도착 간격 지터를 교란**한다는 것을 확인했습니다.
> 결론은 "특정 패킹 전략이 지터를 줄인다"가 아니라 **"관측된 큰 차이는 패킹 단독 효과가 아니라 배경 트래픽의 시간 구조에서 비롯된다"**로 정정되었고, 이 결과를 **2026 한국자동차공학회 추계학술대회 Full Paper로 제출(Submitted, 2026-09)**했습니다.

## 1. 왜 3-node인가

| 측면 | 초기 2-node (루트) | 최종 3-node (`final_campaign/`) |
|---|---|---|
| 토폴로지 | 제어 TX 노드가 배경 dummy도 생성 | **Node1 제어 TX / Node2 독립 배경 TX / Node3 RX** 분리 |
| 배경 트래픽 | 제어 노드의 같은 CAN controller mailbox·스케줄 공유 | 별도 RA6M5 ECU에서 생성 (same-MCU 교란 제거) |
| 측정 | PCAN Listen-Only, 고정 payload | 동일 (PCAN Listen-Only, byte-identical 고정 payload) |
| 데이터 | 3전략 × 4부하 × 10 run = 120 TRC (n=10) | 파일럿 n=1(12조건) → 반복 n=5 → gap sweep → fixed-BG 확인 |

## 2. 하위 분석 (각 폴더가 독립 산출물)

| 폴더 | 내용 | 비고 |
|---|---|---|
| [`analysis/pilot_run1/`](analysis/pilot_run1) | 12조건 × run1 파일럿 (n=1) | 재현 후보일 뿐 유의성 주장 아님 |
| [`analysis/n5/`](analysis/n5) | 12조건 × run1–5 균형 반복 (n=5) | 주 결과. replicate 단위 = run |
| [`analysis/fixed_bg_confirmatory/`](analysis/fixed_bg_confirmatory) | 고정 배경 gap 조건 확인 | old vs new 비교 |
| [`analysis/timing_mechanism/`](analysis/timing_mechanism) | timestamp-only 포렌식 (beat/commensurability) | 인과 주장 **철회 블록 포함** |
| [`analysis/gap_sweep/`](analysis/gap_sweep) | 배경 gap을 직접 쓸어가며 지터 반응 측정 | confirm / response / response_full |
| [`firmware/`](firmware) | 3-node용 사용자 작성 src (FSP 제외) | 아래 3절 |

## 3. firmware

[`firmware/`](firmware)에는 3-node 구성에 사용한 **사용자 작성 `src` 파일만** 포함합니다 (`hal_entry.c`, `canfd_signalset_64b.h`, 역할 분리용 `three_node_experiment_config.h`). Renesas FSP 생성 트리(`ra/`, `ra_gen/`), 빌드 산출물, 디바이스 바이너리, IDE 메타데이터는 공개 대상이 아닙니다. 자세한 내용은 [`firmware/README.md`](firmware/README.md).

## 4. 관측된 주요 결과 (초기 관찰이 아니라 최종 재실험)

> 수치는 `analysis/n5/3node_n5_analysis.md`, `analysis/timing_mechanism/timing_mechanism_analysis.md`의 요약이며, 원본 TRC가 있어야 재현됩니다.

- 60-target 반복(n=5) 지터: **A60 30.22 ± 16.02 µs** (run1 outlier가 지배), **B60 61.61 ± 0.28 µs**, **C60 24.78 ± 0.65 µs**.
- A60 − C60 matched-index 평균 = **+5.45 ± 16.03 µs** (초기 2-node n=10의 +37.7 µs와 달리 run마다 부호가 뒤집힘).
- 포렌식 분석: 큰 지터는 **배경 gap과 5 ms 주기의 commensurability(beat)**와 연관되며, 다중 프레임 패킹(A·B)은 beat에 취약하고 단일 프레임 패킹(C)은 둔감. 단, PCAN timestamp는 bus-monitor 도착 시각이지 SOF/release가 아니므로 **association(연관)**까지만 주장합니다.
- 80 % 부하에서는 전략과 무관하게 67–71 µs로 수렴(blocking saturation).

**말할 수 없는 것:** 중재(arbitration)를 직접 측정한 인과, release/mailbox 대기시간, 단일 요인(프레임 길이 또는 write 수) 단독 인과, C의 보편적 우위. 상세 claim boundary는 각 하위 폴더의 `*.md`에 있습니다.

## 5. 재현

각 하위 폴더의 `analyze_*.py`는 비공개 원본 TRC 디렉터리를 입력으로 받습니다. 공개된 것은 분석 script, 요약 table(CSV), 리포트(MD), 파생 그림(PNG)뿐이며, **원시 TRC와 대용량 per-frame 중간 CSV(`interarrival_samples.csv`, `phase_samples.csv`, `predecessor_context.csv`)는 용량·원본 보호를 이유로 제외**했습니다. parser 입력 형식은 루트의 [`sample_data/`](../sample_data)와 동일합니다(3-node는 별도 노드가 보내는 ID 0x300–0x30F 배경 프레임이 추가될 뿐).

## 6. Attribution 및 공개 상태

이 자료는 루트 저장소와 동일하게 **팀·연구실 공동 연구 자료**입니다. 저장소 소유자가 2026-10-21 공동 연구진의 공개 동의를 확인했습니다. 공개 Git history는 공개 후보 package 시점부터 시작하므로 firmware·분석 source 전체의 최초 작성자를 증명하지 않으며, **공동 연구 source를 단독 저작물로 주장하지 않습니다.** 소프트웨어 license는 선정하지 않았으므로 **All rights reserved**입니다. 실제 TRC, scope 원본, FSP 생성물, 연구실 내부 문서·개인정보 자료는 공개 대상이 아닙니다.

---

## English summary

This folder holds the public-safe source and analysis artifacts of the **final (3-node) re-experiment** that followed the repository's initial **2-node** campaign in the root.

In the initial campaign the control TX node also generated the background (dummy) load, so the large receive-jitter differences between packing strategies could not be cleanly attributed to packing. We re-ran the experiment with a dedicated **external Background TX node** (Node1 Control TX / Node2 Background TX / Node3 RX, PCAN Listen-Only) and found that matching bus load also shifts the **background generation gap**, which perturbs arrival jitter through a **commensurability beat** with the 5 ms control period — multi-frame packing (A, B) is beat-susceptible, single-frame packing (C) is not.

Repeated n=5 results at 60 % target: A60 30.22 ± 16.02 µs, B60 61.61 ± 0.28 µs, C60 24.78 ± 0.65 µs; the A60−C60 matched-index mean is +5.45 ± 16.03 µs (vs +37.7 µs in the 2-node n=10 run). All causal language is bounded: PCAN timestamps are bus-monitor arrival times, so only **association** is claimed, not arbitration cause. These results were **submitted** as a Full Paper to the 2026 KSAE Autumn Conference. This is **joint team/lab research** (co-researcher release consent confirmed 2026-10-21); no license is granted (**all rights reserved**), and raw TRC, scope originals, and FSP-generated trees are excluded.
