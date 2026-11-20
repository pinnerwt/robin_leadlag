"""Change calldata discount and synthetic inventory independently; offline only."""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from routera3d_price import price_word, first_reverse_discount, reverse_v3_limit
from v3_calldata import word, signed
from probe_routera3d import ROUTER


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('seed'); a = ap.parse_args()
    seed = json.load(open(a.seed))
    reference = json.load(open('tests/fixtures/routera3d_price.json'))[0]
    tx = next(r['tx'] for r in map(json.loads, open('reports/amm/optimistic-target-corpus.jsonl')) if r['tx']['tx'] == reference['tx'])
    key = '0x70a08231'+int(ROUTER, 16).to_bytes(32, 'big').hex()
    results = []
    with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
        for inventory in [10**10, 10**11, 10**12]:
            seed['getters']['0x5fc5360d0400a0fd4f2af552add042d716f1d168'][key] = '0x'+inventory.to_bytes(32, 'big').hex()
            Path(tmp.name).write_text(json.dumps(seed))
            requests = []
            for discount in [1, 9, 10, 31]:
                raw = bytearray.fromhex(tx['data'][2:]); raw[14] = 256-discount
                requests.append(dict(tx, data='0x'+raw.hex()))
            output = subprocess.check_output(['target/release/examples/router_prefix', tmp.name],
                input=''.join(json.dumps(t)+'\n' for t in requests), text=True)
            rows = list(map(json.loads, output.splitlines())); assert len(rows) == len(requests)
            for request, row in zip(requests, rows):
                assert row['error'] is None
                calls = [c for c in row['calls'] if c['data'].startswith('0x128acb08')]
                assert len(calls) == 1 and len(row['calls']) == 1
                d = bytes.fromhex(calls[0]['data'][10:]); discount = first_reverse_discount(request['data'])
                assert word(d, 1) == 0 and signed(word(d, 2)) == inventory
                limit = reverse_v3_limit(price_word(request['data']), discount, 100, 10)
                assert limit == word(d, 3)
                results.append(dict(inventory=str(inventory), discount=discount, amount=str(signed(word(d, 2))), limit=str(limit)))
    Path('reports/amm/routera3d-interventions.json').write_text(json.dumps(dict(cases=results,
        caveat='Synthetic independent prefix experiments; not historical balances or settlement'), indent=2)+'\n')
    print('12 independent inventory/discount interventions match amount and bound')

if __name__ == '__main__':
    main()
