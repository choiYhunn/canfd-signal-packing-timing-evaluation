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

## 4. 결론까지의 근거 (60 % 목표 부하, 0x100 inter-arrival jitter)

아래 수치는 모두 이 저장소의 요약표에서 나온 값이며, [`../tools/verify_headline_numbers.py`](../tools/verify_headline_numbers.py)가 CSV에서 다시 계산해 확인합니다.

| 단계 | 조건 | 결과 | 근거 파일 |
|---|---|---|---|
| ① 초기 비교 (2-node, n=10) | 배경 frame을 제어 노드가 함께 생성. source 기본 gap A60 240 µs, C60 238 µs | A60 59.764 µs, C60 22.098 µs → **차이 37.667 µs** | [`../analysis/summary_tables/condition_summary.csv`](../analysis/summary_tables/condition_summary.csv) |
| ② 3-node 반복 (n=5) | 독립 배경 노드. 전략별 nominal gap A 240 / B 235 / C 238 µs | A60 30.22 ± 16.02, B60 61.61 ± 0.28, C60 24.78 ± 0.65 µs. A60은 run1(58.88)만 크고 run2–5는 22.5–23.5. **B60 − C60 = 36.83 µs** | [`analysis/n5/`](analysis/n5) |
| ③ 같은 전략, gap만 변경 (n=3) | 전략 A만 사용, run마다 보드 리셋, 측정 순서 교란 | gap 238 → **26.37 ± 0.26**, 240 → **56.84 ± 0.16**, 244 → 75.96 ± 0.31, 250 → 21.83 ± 0.25 µs | [`analysis/gap_sweep/confirm/`](analysis/gap_sweep/confirm) |
| ④ 230–250 µs sweep (A/B/C, gap당 n=1, 탐색용) | 같은 펌웨어에서 배경 gap만 변경 | A: 238 → 242 µs에서 25.49 → **73.57 µs**, 재구성 점유율 −0.95 pp. C도 26.58 → 73.89 µs로 같은 방향 | [`analysis/gap_sweep/response_full/`](analysis/gap_sweep/response_full) |

해석:

- ③에서 **전략을 고정하고 gap만 2 µs 바꿔도 지터가 약 30 µs 달라졌습니다.** ①·②의 전략 간 차이(약 37 µs)와 같은 크기이므로, 전략마다 gap이 달랐던 비교에서 그 차이를 패킹 효과로 볼 수 없습니다.
- ④에서 세 전략 모두 gap에 대해 비단조적으로 반응했고, 재구성 점유율은 1 pp 안쪽으로만 변했습니다. 그래서 결론은 **"평균 점유율이 같아도 배경 트래픽의 생성 간격이 다르면 타이밍 조건이 같지 않다"**입니다. 특정 패킹 전략의 우위는 주장하지 않습니다.
- ②의 nominal gap은 source의 기본값이고, 측정 중 약 ±1 µs를 실시간으로 조정했지만 run별 값은 기록하지 못했습니다([`analysis/n5/3node_n5_analysis.md`](analysis/n5/3node_n5_analysis.md)).
- [`analysis/timing_mechanism/`](analysis/timing_mechanism)은 timestamp만으로 본 포렌식입니다. B60은 run 간 재현되는 강한 자기상관(ACF ≈ 0.84), C60은 거의 무상관(ACF ≈ 0.07)을 보였지만, 이를 원인으로 설명하던 commensurability 해석은 그 문서 안에서 **철회**했습니다. 연관만 기록합니다.
- 80 % 목표에서는 세 전략이 67–71 µs로 비슷했습니다(n=5).

> **정정 (2026-10-23):** 이 절의 이전 버전은 "단일 프레임 패킹(C)은 beat에 둔감"이라고 적었습니다. 이는 철회된 해석에서 온 문장이고, ④에서 C도 gap에 크게 반응하므로 삭제했습니다.

## 5. 측정한 것과 하지 않은 것

| 지표 | 정의 | 이 연구에서 |
|---|---|---|
| Inter-arrival jitter | 연속한 0x100 도착 간격의 표준편차 (PCAN listen-only timestamp) | **측정** — 주 지표 |
| Reconstructed occupancy | frame 길이·bitrate 모델로 계산한 버스 점유율 | **모델 계산** — 측정값 아님 |
| PCAN Mean Bus Load | 계측기가 표시하는 실측 부하 | **저장 안 함** — gap 보정 때만 참고했고, 세 캠페인 run 표의 실측 부하 열은 모두 비어 있음 |
| One-way latency | 송신 요청부터 수신까지 | **측정 안 함** |
| WCRT | 최악 응답 시간 분석 | **하지 않음** |

PCAN timestamp는 bus monitor가 본 도착 시각이며 SOF나 application release 시각이 아닙니다.

## 6. 재현 범위

| 범위 | 공개 자료만으로 | 방법 |
|---|---|---|
| README의 핵심 수치 | **가능** | `python tools/verify_headline_numbers.py` (저장소 루트, 표준 라이브러리만) |
| 요약표·그림 다시 만들기 | 불가 | 각 폴더의 `analyze_*.py`가 비공개 원본 TRC를 입력으로 받음 |
| 펌웨어 빌드 | 불가 | FSP 생성 트리·프로젝트 설정 미포함 |

원시 TRC와 대용량 per-frame 중간 CSV(`interarrival_samples.csv`, `phase_samples.csv`, `predecessor_context.csv`)는 용량과 공동연구 원본 보호를 이유로 제외했습니다. parser 입력 형식은 루트의 [`sample_data/`](../sample_data)와 같습니다(3-node는 별도 노드가 보내는 ID 0x300–0x30F 배경 frame이 추가됨).

## 7. Attribution 및 공개 상태

이 자료는 루트 저장소와 동일하게 **팀·연구실 공동 연구 자료**입니다. 저장소 소유자가 2026-10-21 공동 연구진의 공개 동의를 확인했습니다. 공개 Git history는 공개 후보 package 시점부터 시작하므로 firmware·분석 source 전체의 최초 작성자를 증명하지 않으며, **공동 연구 source를 단독 저작물로 주장하지 않습니다.** 소프트웨어 license는 선정하지 않았으므로 **All rights reserved**입니다. 실제 TRC, scope 원본, FSP 생성물, 연구실 내부 문서·개인정보 자료는 공개 대상이 아닙니다.

---

## English summary

This folder holds the public-safe source and analysis artifacts of the **final (3-node) re-experiment** that followed the repository's initial **2-node** campaign in the root.

In the initial campaign the control TX node also generated the background (dummy) load, and the background gap differed by strategy (A60 240 µs vs C60 238 µs in the source defaults), so the 37.667 µs A60–C60 jitter difference could not be attributed to packing. We re-ran the experiment with a dedicated **external Background TX node** (Node1 Control TX / Node2 Background TX / Node3 RX, PCAN listen-only). With strategy A fixed, changing only the configured background gap from 238 to 240 µs moved jitter from 26.37 ± 0.26 to 56.84 ± 0.16 µs (n = 3, board reset and permuted order per run) — the same size as the earlier strategy difference. A 230–250 µs sweep gave a strongly non-monotonic response for all three strategies while reconstructed occupancy changed by less than 1 pp (e.g. strategy A, 238 → 242 µs: 25.49 → 73.57 µs, −0.95 pp). Conclusion: average occupancy alone does not establish equivalent timing conditions; no packing strategy is claimed superior. Every number here is recomputed from the published CSVs by `tools/verify_headline_numbers.py`.

Measured vs not: inter-arrival jitter is measured from PCAN timestamps; occupancy is reconstructed from a frame-length model; measured PCAN bus load was not stored; one-way latency and WCRT were not measured. A timestamp-only forensic found strong, run-reproducible autocorrelation for B60 and near-white error for C60, but its commensurability explanation was retracted in that document, so only the association is reported. (An earlier version of this summary said single-frame packing was immune to the beat; that came from the retracted interpretation and is contradicted by the sweep.) These results were **submitted** as a Full Paper to the 2026 KSAE Autumn Conference. This is **joint team/lab research** (co-researcher release consent confirmed 2026-10-21); no license is granted (**all rights reserved**), and raw TRC, scope originals, and FSP-generated trees are excluded.
