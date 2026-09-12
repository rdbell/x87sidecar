# Native-state boundary conversion investigation

PR #32's native-state conversion has measurable cost in isolated x87
benchmarks. The optimization described here reduces that cost without
removing the conversion or changing its numerical algorithms. It does not
yet establish that PR #32 caused the previously observed 11–12% FFXI FPS
regression: repeated game runs of the same build varied more than that.

## Implementation and correctness

Based on development `c00c5f7c2de0c04728e53ce08af225c608c47ec1`:

- Read and collapse the tag word once, then test occupied slots with TBZ.
- Exit after the last occupied slot instead of scanning the remaining empties.
- Load binary64 bits directly into a GPR on export, eliminating an FP
  load/register-transfer pair and the boundary's FPR allocation.
- Keep the bitmap in the low half of the saved flags register, preserving
  the existing seven-GPR scratch budget.

Both boundary conversions remain in place. Slot order, native payload
layout, numerical conversion, and signal-visible state are unchanged.
This preserves PR #32's native-layout correction; it does not claim full
80-bit arithmetic internally, which still uses the existing binary64 model.

The final build passed `bash scripts/run_tests.sh --no-build`: **1,021 passed,
zero failed, two known stock-Rosetta divergences, zero skipped / 1,023** in
216.091 seconds, under a 600-second outer cap. The matrix includes native,
signal/context, direct translator, fusion, bridging, and register-pressure
coverage. The added native-state regression exercises all 256 occupancy
masks at all eight TOP rotations using normal numbers, signed zero,
subnormal, infinities, and quiet NaN, checking occupied FXSAVE payloads and
tags/TOP after FXRSTOR and separate translation replies.

## Native benchmark results

Apple M2 Max, macOS 26.5 (25F71), 2026-09-12. Identical benchmark executables,
three loaders, six repetitions with rotating variant order: 54 successful
invocations. Each invocation has a 45-second cap plus bounded cleanup.
The table compares medians of the benchmark's reported elapsed nanoseconds;
negative means less time. These are benchmark timings, not FPS predictions.

| Benchmark case | Optimized vs current | Conversion disabled vs current |
| --- | ---: | ---: |
| fld/fstp m32 singles | -17.99% | -31.66% |
| fld/fstp m64 singles | -19.04% | -26.06% |
| fld/fst/fstp singles | +1.05% | -23.02% |
| fld32/fstp64 singles | -17.69% | -29.62% |
| fld64/fstp32 singles | -22.67% | -35.16% |
| padded m32 | -9.39% | -32.36% |
| dot product n3 | -5.93% | -18.96% |
| dot product n4 | -1.88% | -14.55% |
| dot product n8 | -2.57% | -6.64% |
| F2XM1 | +2.39% | -11.33% |

The conversion-disabled control only adds an immediate return to
`emit_native_state_boundary`. It is **unsafe, diagnostic only**, and excluded
from this change. Removing conversion also changes generated code layout;
the comparison is not a cycle-by-cycle decomposition. Small changes in the
triple-op and F2XM1 cases overlap the observed variation. There is no claim
of a universal speedup.

Run a comparison from this checkout with separately built loaders:

```sh
python3 scripts/compare_benchmarks.py \
  --variant current=/absolute/current/build/bin/x87sidecar_entitled \
  --variant optimized=/absolute/optimized/build/bin/x87sidecar_entitled \
  --bin-dir build/bin/bench --output /tmp/new-boundary-comparison --repeats 6
python3 -m unittest discover -s scripts -p test_compare_benchmarks.py
```

The runner removes inherited X87_/ROSETTA_ settings, hashes loaders and
executables, records every invocation, checks BENCH rows, and waits for pipe
EOF as well as loader exit. Two lifecycle tests cover a target outliving its
loader and cleanup after a target timeout. Keep game runs and other
benchmarks stopped while measuring.

## FFXI integration evidence

Only Hxitest on local Docker LSB was used. The installed app was preserved;
candidate apps and a cloned Wine prefix were used for tests. All variants
used the same cx-26.3.0-1 Wine runtime with the existing locale patch, mtld3d,
shader seed, addon fixture, camera, draw distance 20, noon clock command,
4096 x 4096 background, and 1882 x 1058 menu/output resolution. FPS was
uncapped. Captures used standard-nosample without profiling or packet capture,
with a 300-second game cap and 40-second city holds. Reported scene FPS uses
approximately 37 seconds of complete measured windows after settling.

All six runs passed the report's scene/coverage checks and matched fixture,
graphics, renderer, and shader-seed hashes. Results in execution order:

| Run | Markets FPS | Mines FPS |
| --- | ---: | ---: |
| current 1 | 68.190 | 144.472 |
| conversion disabled 1 (unsafe control) | 47.414 | 96.324 |
| current 2 | 46.439 | 102.795 |
| optimized 1 | 47.926 | 120.255 |
| current 3 | 55.351 | 121.767 |
| optimized 2 | 57.696 | 127.132 |

The final adjacent pair improved 4.2% / 4.4%, but earlier repeats do not
support treating those percentages as a reliable gain. Screenshots of both
optimized runs show the expected character, geometry, and UI with no obvious
rendering defect. They also show different sky conditions: the noon command
does not hold the calendar date or weather fixed. That is an additional
comparison gap not detected by the current report's scene checks. No effects
or crowded-player stress fixture was run in this investigation.

The host had unrelated airportd, virtualization, WindowServer and T3 work.
Those processes were left alone. AC power was present and no thermal warning
was recorded. Matching fixture and renderer hashes do not establish matching
host scheduling. The unchanged build's first two repeats alone differed by
about 32% in Markets, exceeding the suspected regression. A paired comparison
on a quiet host with fixed weather/calendar state is needed before assigning
a reliable gameplay percentage. These runs neither confirm nor exonerate
PR #32 as the cause of the earlier FFXI regression.

## Rejected approaches and evidence locations

- A backward-branch runtime loop was rejected before implementation because
  Rosetta signal recovery cannot step it.
- Packing slot bits into saved NZCV without clearing them caused signal
  decode failures. Clear the low 16 bits before restoring flags.
- Masking saved flags to `0xf0000000` passed a focused subset but failed nine
  FCOMI checks in the full matrix. It discards Rosetta parity at bit 26;
  `0xffff0000` passed the final full matrix.
- The first comparison runner waited only for loader exit, allowing targets
  to overlap. Its data was invalidated. Final results wait for descendant
  stdout EOF and use bounded process-group cleanup.

Local evidence lives in `ximac/benchmarks/20260912-x87-boundary/`:
`full-tests.log`, `full-tests-driver.log`, `final-native-bench/{summary,runs,identities}.json`,
`city-*-report.json`, each run's `restoration.json`, and `sidecar-identities.json`.
The earlier `native-bench-summary.json` is an intermediate prototype result;
`invalid-overlapped-native-bench/` is invalid. Neither supports the final table.
Raw game logs and client snapshots remain local.

## Baseline and rollback

`known-good/` under that evidence directory contains APFS copies of the
installed app, runtime, prefix, and exported launcher preferences, plus
`manifest.json` with source/backup locations and hashes. The installed
cooperative sidecar is
`ce7280c00265e53a6989be0dd545ddc2c76245ecab99d1373f7eb93aa4731ed3`.
The final optimized cooperative sidecar used for tests is
`d659410c0c576fc093086ebdd872b7bcb84442fbe1f6585ea3585f97138c0a2a`.

This source change does not update `/Applications/FFXI-on-Mac.app` or its
runtime. No installed rollback is necessary. If a later installation needs
rollback, stop the game first, retain that installation separately, and
restore the app from `known-good/FFXI-on-Mac.app`; restore runtime/prefix only
if those were changed too. Import the saved preferences into
`org.batesai.horizonxi-on-mac` only if restoring those settings is intended.
Verify against the manifest before relaunching. Never restore over a running
game or discard newer character settings without review.
