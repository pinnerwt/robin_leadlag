"""Offline compressed dispatcher probe; authorization assumed, no state commit.
Seed is explicit: do not silently fetch missing accounts/slots or assume zeros.
"""
import argparse
import collections
import json
import subprocess
from pathlib import Path

ROUTER = '0x000000000000a3d2e62895f55d5a4304d2f3c998'

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('seed')
    p.add_argument('--corpus', default='reports/amm/optimistic-target-corpus.jsonl')
    p.add_argument('--output', default='reports/amm/routera3d-child-prefix.jsonl')
    a = p.parse_args()
    txs = [r['tx'] for r in map(json.loads, open(a.corpus))
           if (r['tx']['to'] or '').lower() == ROUTER]
    result = subprocess.run(['target/release/examples/router_prefix', a.seed],
        input=''.join(json.dumps(t)+'\n' for t in txs), text=True,
        capture_output=True, check=True)
    Path(a.output).write_text(result.stdout)
    counts = collections.Counter()
    for row in map(json.loads, result.stdout.splitlines()):
        counts[row['error'] or str([(c['to'], c['data'][:10]) for c in row['calls']])] += 1
    print(json.dumps(dict(counts), indent=2))

if __name__ == '__main__':
    main()
