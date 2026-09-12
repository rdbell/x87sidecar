#!/usr/bin/env python3
"""Compare sidecar builds using identical benchmark executables and bounded runs.

Example: --variant current=/path/x87sidecar_entitled --variant candidate=/path/other
         --bin-dir build/bin/bench --output /tmp/comparison
The output directory must be new. Keep game runs and other benchmarks stopped.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import statistics
import subprocess
import time


def run(command, log, timeout):
    env = {k: v for k, v in os.environ.items() if not k.startswith(('X87_', 'ROSETTA_'))}
    started = time.monotonic()
    # The loader can exit before its target. EOF includes descendants holding
    # stdout; waiting for just the loader would overlap the next benchmark.
    proc = subprocess.Popen([str(x) for x in command], env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, start_new_session=True)
    try:
        output, _ = proc.communicate(timeout=timeout)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            output, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            output, _ = proc.communicate(timeout=5)
        code = 124
    log.write_bytes(output)
    return {'exit': code, 'seconds': round(time.monotonic() - started, 3), 'log': log.name}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant', action='append', required=True, metavar='NAME=LOADER')
    parser.add_argument('--bin-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=3, choices=range(1, 11))
    parser.add_argument('--timeout', type=int, default=45, choices=range(1, 121))
    parser.add_argument('benchmarks', nargs='*', default=['bench_single_op', 'bench_dot_product', 'bench_f2xm1'])
    args = parser.parse_args()
    variants = {}
    for value in args.variant:
        name, sep, path = value.partition('=')
        if not sep or not re.fullmatch(r'[A-Za-z0-9_-]+', name) or name in variants:
            parser.error('Variants must have unique simple names and NAME=LOADER paths')
        variants[name] = Path(path).resolve(strict=True)
    if len(variants) < 2:
        parser.error('At least two variants are required')
    binaries = {name: (args.bin_dir / name).resolve(strict=True) for name in args.benchmarks}
    if any(Path(name).name != name for name in binaries):
        parser.error('Benchmark names must be filenames within --bin-dir')
    args.output.mkdir(parents=True, exist_ok=False)
    identities = {label: {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
                  for label, paths in [('loaders', variants), ('benchmarks', binaries)]}
    (args.output / 'identities.json').write_text(json.dumps(identities, indent=2) + '\n')
    results, samples = [], {}
    names = list(variants)
    for repeat in range(args.repeats):
        offset = repeat % len(names)
        order = names[offset:] + names[:offset]
        for bench, binary in binaries.items():
            for name in order:
                log = args.output / f'{repeat + 1}-{bench}-{name}.log'
                result = run([variants[name], binary], log, args.timeout)
                result.update(repeat=repeat + 1, benchmark=bench, variant=name)
                results.append(result)
                (args.output / 'runs.json').write_text(json.dumps(results, indent=2) + '\n')
                print(json.dumps(result), flush=True)
                rows = re.findall(r'^BENCH\s+(\S+)\s+(\d+)\s*$', log.read_text(errors='replace'), re.M)
                if result['exit'] != 0 or not rows or len({r[0] for r in rows}) != len(rows):
                    raise SystemExit(f'Failed or malformed benchmark: {log}')
                for case, ns in rows:
                    samples.setdefault(case, {}).setdefault(name, []).append(int(ns))
    summary = {}
    for case, values in samples.items():
        if set(values) != set(names) or any(len(v) != args.repeats for v in values.values()):
            raise SystemExit(f'Missing benchmark samples: {case}')
        medians = {name: statistics.median(v) for name, v in values.items()}
        summary[case] = {'nanoseconds': values, 'median_nanoseconds': medians,
                         'time_change_percent': {name: round(100 * (v / medians[names[0]] - 1), 2)
                                                 for name, v in medians.items()}}
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')


if __name__ == '__main__':
    main()
