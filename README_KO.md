
# CAN-FD Signal Packing Timing Evaluation

> 핵심 결과: A60 jitter 59.764 us, C60 jitter 22.098 us, 차이 37.667 us. Reconstructed occupancy 차이는 -0.091382 pp로 strict-matched였고, 120/120 QC PASS, gap >6 ms = 0, frame-loss candidate = 0이었다.

## 1. 연구 질문

동일한 64B mixed-period signal workload를 여러 CAN-FD frame으로 분산하거나 하나로 packing할 때 RX inter-arrival jitter와 tail behavior가 어떻게 달라지는지 평가한다.

## 2. 64B mixed-period workload와 A/B/C layout

- A: 5 ms에 0x100 8B, 0x101 8B, 0x102 16B; 50 ms에 0x110 8B, 0x120 8B, 0x130 16B
- B: 5 ms에 0x100 32B; 50 ms에 0x110 32B
- C: 5 ms에 0x100 64B. normal signal도 5 ms마다 반복

## 3. RA6M5 TX/RX 구현

Renesas RA6M5 기반 TX/RX에서 동일 strategy 쌍을 사용했다. TRC 최종 campaign은 `meas_64b_fixed`, Scope campaign은 `pwm_endpoint_64b_marker_fixed` 변형이다.

## 4. PCAN TRC와 Scope 분리

TRC 분석은 0x100 RX inter-arrival jitter이며 one-way latency가 아니다. Scope는 별도 campaign에서 CH1 Tpre, CH2 Ttx, CH3 Trx, CH4 Tpwm_sw marker를 측정했다.

## 5. Fixed payload 공정성

동일 ID의 반복 payload를 byte-identical로 고정해 bit stuffing pattern 변화를 packing 효과와 혼동하지 않도록 했다.

## 6. n=10 / 120 TRC

3 strategies × 4 conditions(baseline/30/60/80%) × 10 runs = 120 TRC를 분석했고 모든 layout/payload/QC gate를 통과했다.

## 7. A60-C60 및 80% gate

A60-C60 jitter 차이는 37.667 us이고 bootstrap CI는 [37.466, 37.857] us다. A60/C60 reconstructed occupancy는 63.250300%/63.341682%로 strict-matched다. 80%에서는 A/B/C 67.034/69.490/73.799 us였지만 full-ordering claim gate는 FAIL이므로 완전한 순서를 주장하지 않는다.

## 8. Scope 결과

`D_wr2rx`는 121.6/234.1/377.7 us, `D_rx2pwm`은 3.00/3.06/3.16 us였다. 이는 marker-to-marker delay이며 실제 PWM edge 또는 pure bus latency가 아니다.

## 9. 주장하지 않는 범위

모터 안정성, PID 진동, pure bus latency, PCAN actual load, 80% full ordering, blocking 단일 원인을 입증하지 않는다.

부하용 dummy frame은 동일한 TX node에서 생성했으므로, 결과를 순수한 외부 bus contention 효과로 해석할 수 없다.

## 10. 재현 방법

`analysis/scripts/run_analysis_relative.ps1` 또는 Python script를 사용한다. 최종 수치 재현에는 비공개 120-TRC 원본과 manifest가 필요하다. 공개 sample은 형식 확인용 synthetic data다.

## 11. 저장소 구조와 공개 범위

- `firmware`: 사용자 작성 TX/RX 소스 후보
- [`analysis`](analysis/): 분석 script, 상대경로 config, [summary table](analysis/summary_tables/), [figure](analysis/figures/)
- [`sample_data`](sample_data/): synthetic example
- `docs`: architecture, experiment design, limitations

원본 TRC, 원본 Scope CSV, build output, 제출 양식, 개인정보 포함 PDF와 vendor 문서는 공개 후보에서 제외했다.

## 12. 향후 연구

동기화된 bus-level instrumentation, actual load capture, 더 다양한 bit pattern과 arbitration scenario, motor/PWM physical output 측정을 별도 실험으로 확장할 수 있다.
