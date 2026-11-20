"""Rebuild explicitly mixed-era research seed, entirely offline.
Only parent authorization is synthetic; child code/config come from the pinned
research artifact. Never use this seed for historical state or live quotes.
"""
import argparse
import json
from pathlib import Path
from probe_routera3d import ROUTER


def build(archived, child, authorization_trace):
    seed = archived
    authorized = set()
    for row in authorization_trace:
        for h in row.get('hash_preimages', []):
            raw = bytes.fromhex(h['preimage'][2:])
            if h['storage_address'].lower() == ROUTER and len(raw) == 64 and int.from_bytes(raw[32:], 'big') == 3:
                authorized.add(h['hash'])
    if len(authorized) != 5:
        raise ValueError('expected five observed mapping-3 authorization keys')
    for key in authorized:
        seed['accounts'][ROUTER]['storage'][key] = '0x1'
    address = child['address']
    seed['accounts'][address] = dict(code=child['code'], storage=child['storage'], balance='0x0', nonce=0)
    seed.update(trace_execution=True, trace_calldata=True, trace_hashes=True, execute_targets=[address])
    seed['research_only'] = dict(child_block=child['block'], child_hash=child['anchor_hash'],
        synthetic='five parent authorization flags and child account balance/nonce',
        limitation='mixed-era routing probe; missing external getters are unresolved, not zero state')
    return seed


def with_price_probe(seed, pools, inventory):
    seed['execute_targets'].append(ROUTER)
    seed['math_targets'] = [seed['execute_targets'][0]]
    for pool in pools:
        address = pool['pool']
        value = int(seed['accounts'][address]['storage']['0x0'], 16)
        fields = [value & ((1 << 160)-1), (value >> 160) & ((1 << 24)-1),
                  (value >> 184) & 65535, (value >> 200) & 65535,
                  (value >> 216) & 65535, (value >> 232) & 255, (value >> 240) & 255]
        if fields[1] >> 23:
            fields[1] += (1 << 256) - (1 << 24)
        seed.setdefault('getters', {}).setdefault(address, {})['0x3850c7bd'] = '0x'+''.join(x.to_bytes(32, 'big').hex() for x in fields)
    for token, amount in [('0x5fc5360d0400a0fd4f2af552add042d716f1d168', inventory),
                          ('0x0bd7d308f8e1639fab988df18a8011f41eacad73', 0)]:
        data = '0x70a08231'+int(ROUTER, 16).to_bytes(32, 'big').hex()
        seed.setdefault('getters', {}).setdefault(token, {})[data] = '0x'+amount.to_bytes(32, 'big').hex()
    seed['research_only']['synthetic_inventory'] = dict(USDG=str(inventory), WETH='0')
    return seed


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True)
    p.add_argument('--price-probe', action='store_true')
    a = p.parse_args()
    seed = build(json.load(open('captures/startup-v9-dependencies.json')),
                 json.load(open('reports/amm/routera3d-child-code.json')),
                 map(json.loads, open('reports/amm/routera3d-authorized-prefix.jsonl')))
    if a.price_probe:
        seed = with_price_probe(seed, json.load(open('captures/startup-v9-quotes.json'))['pools'], 10**12)
    Path(a.output).write_text(json.dumps(seed)+'\n')

if __name__ == '__main__':
    main()
