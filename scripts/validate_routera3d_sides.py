"""Offline direction-mask audit and independent synthetic sell-bound experiments."""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from routera3d_price import PRICE_XOR, route_fields, forward_v3_limit, forward_input_amount
from v3_calldata import word, signed


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('seed'); a = ap.parse_args()
    corpus = [r for r in map(json.loads, open('reports/amm/optimistic-target-corpus.jsonl'))
              if (r['tx']['to'] or '').lower() == '0x000000000000a3d2e62895f55d5a4304d2f3c998']
    directions = []; headers = []
    for row in corpus:
        tx = row['tx']; fields = route_fields(tx['data'])
        headers.append(dict(tx=tx['tx'], calldata=tx['data'], expected=fields))
        for log in row['logs']:
            if log['address'].lower() != '0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca':
                continue
            assert fields['routes'][0]['index'] == 0
            zero = signed(word(bytes.fromhex(log['data'][2:]), 0)) > 0
            assert (fields['routes'][0]['side'] == 2) == zero
            directions.append(dict(tx=tx['tx'], zero=zero))
    assert len(headers) == 85 and len(directions) == 79
    seed = json.load(open(a.seed))
    key = '0x70a08231000000000000000000000000000000000000a3d2e62895f55d5a4304d2f3c998'
    seed['getters']['0x0bd7d308f8e1639fab988df18a8011f41eacad73'][key] = '0x'+(10**18).to_bytes(32, 'big').hex()
    reference = json.load(open('tests/fixtures/routera3d_price.json'))[0]
    tx = next(r['tx'] for r in corpus if r['tx']['tx'] == reference['tx'])
    requests = []
    for price in [1700000000, 1750000000, 1800000000]:
        for discount in [1, 9, 10, 31]:
            for cap in [(131071, 110), (65536, 10)]:
                raw = bytearray.fromhex(tx['data'][2:])
                raw[1:6] = int(f'{price ^ PRICE_XOR:040b}'[::-1], 2).to_bytes(5, 'big')
                raw[6:9] = ((cap[0] << 7) | cap[1]).to_bytes(3, 'big')
                raw[14] = 256-discount; raw[-2:] = bytes.fromhex('0002')
                requests.append(dict(tx, data='0x'+raw.hex()))
    with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
        Path(tmp.name).write_text(json.dumps(seed))
        output = subprocess.check_output(['target/release/examples/router_prefix', tmp.name],
            input=''.join(json.dumps(t)+'\n' for t in requests), text=True)
    rows = list(map(json.loads, output.splitlines())); assert len(rows) == len(requests)
    cases = []
    for request, row in zip(requests, rows):
        assert row['error'] is None
        assert len(row['calls']) == 1 and row['calls'][0]['data'].startswith('0x128acb08')
        d = bytes.fromhex(row['calls'][0]['data'][10:]); fields = route_fields(request['data'])
        discount = -fields['routes'][0]['adjustment']
        expected = forward_v3_limit(fields['price'], discount, 100, 10)
        assert word(d, 1) == 1
        assert word(d, 3) == expected, (word(d, 3), expected)
        adjusted = fields['price'] * (100000-discount) // 100000
        amount_cap = fields['cap'] * 10**18 // adjusted
        assert signed(word(d, 2)) == min(10**18, amount_cap)
        assert signed(word(d, 2)) == forward_input_amount(request['data'], 10**18)
        cases.append(dict(calldata=request['data'], limit=str(expected), amount=str(signed(word(d, 2)))))
    report = dict(header_matches=len(headers), direction_matches=len(directions),
        synthetic_sell_matches=len(cases), directions=directions, cases=cases,
        caveat='Logs validate side only; sell bounds/amounts use mixed-era research seed and synthetic inventory. No historical state or full settlement parity.')
    Path('reports/amm/routera3d-sides-validation.json').write_text(json.dumps(report, indent=2)+'\n')
    Path('tests/fixtures/routera3d_sides.json').write_text(json.dumps(dict(headers=headers, sells=cases), indent=2)+'\n')
    print('85 headers, 79 historical directions, 24 synthetic sell amounts/limits match')

if __name__ == '__main__':
    main()
