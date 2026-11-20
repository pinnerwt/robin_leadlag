"""Independent calldata cap interventions against explicitly synthetic inventory."""
import argparse
import json
import subprocess
from pathlib import Path
from routera3d_price import input_cap
from v3_calldata import word, signed


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('seed'); a = ap.parse_args()
    seed = json.load(open(a.seed))
    key = '0x70a08231000000000000000000000000000000000000a3d2e62895f55d5a4304d2f3c998'
    inventory = int(seed['getters']['0x5fc5360d0400a0fd4f2af552add042d716f1d168'][key], 16)
    reference = json.load(open('tests/fixtures/routera3d_price.json'))[0]
    tx = next(r['tx'] for r in map(json.loads, open('reports/amm/optimistic-target-corpus.jsonl')) if r['tx']['tx'] == reference['tx'])
    requests = []; inputs = []
    for mantissa in [65536, 100000, 131071]:
        for exponent in [0, 10, 20, 40, 110]:
            raw = bytearray.fromhex(tx['data'][2:])
            raw[6:9] = ((mantissa << 7) | exponent).to_bytes(3, 'big')
            requests.append(dict(tx, data='0x'+raw.hex()))
            inputs.append((mantissa, exponent))
    output = subprocess.check_output(['target/release/examples/router_prefix', a.seed],
        input=''.join(json.dumps(t)+'\n' for t in requests), text=True)
    rows = list(map(json.loads, output.splitlines())); assert len(rows) == len(requests)
    cases = []
    for request, row, (mantissa, exponent) in zip(requests, rows, inputs):
        assert row['error'] is None
        assert len(row['calls']) == 1 and row['calls'][0]['data'].startswith('0x128acb08')
        d = bytes.fromhex(row['calls'][0]['data'][10:])
        cap = input_cap(request['data']); amount = signed(word(d, 2))
        assert word(d, 1) == 0 and cap == mantissa << exponent
        assert amount == min(inventory, cap)
        cases.append(dict(calldata=request['data'], mantissa=mantissa, exponent=exponent,
                          cap=str(cap), inventory=str(inventory), amount=str(amount)))
    report = dict(cases=cases, matches=len(cases), caveat=
        'Synthetic inventory and fixed research configuration. Prefix amounts only; no full settlement or universal sizing claim.')
    Path('reports/amm/routera3d-cap-validation.json').write_text(json.dumps(report, indent=2)+'\n')
    Path('tests/fixtures/routera3d_caps.json').write_text(json.dumps(cases, indent=2)+'\n')
    print('15 cap interventions match min(inventory, decoded cap)')

if __name__ == '__main__':
    main()
