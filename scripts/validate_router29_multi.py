"""Recorded-pool-only validation of 29/164cb8f5. Never infer state from logs."""
import collections
import json
from pathlib import Path
from packed_routers import ROUTER_29, decode_packed
from v3_calldata import signed

def main():
    registry=json.load(open('config/optimistic-router-template.json'))
    pools={p['pool'] for p in json.load(open('captures/startup-v9-quotes.json'))['pools']}
    prefixes={r['tx']:r for r in map(json.loads,open('reports/amm/router29-multi-prefix.jsonl'))}
    counts=collections.Counter();fixtures=[];mismatches=[]
    for row in map(json.loads,open('reports/amm/optimistic-target-corpus.jsonl')):
        tx=row['tx']
        if (tx['to'] or '').lower()!=ROUTER_29 or not tx['data'].startswith('0x164cb8f5'):continue
        ops=decode_packed(ROUTER_29,tx['data'],registry,tracked_pools=pools)
        counts['transactions']+=1;counts['decoded_tracked_operations']+=len(ops)
        remaining=list(row['logs'])
        for op in ops:
            log=next((l for l in remaining if l['address'].lower()==op['pool']),None)
            if log is None:counts['predicted_without_log']+=1;continue
            remaining.remove(log)
            raw=bytes.fromhex(log['data'][2:]);v=[int.from_bytes(raw[i:i+32],'big') for i in range(0,160,32)]
            x,y=signed(v[0]),signed(v[1]);filled=max(x,y) if op['amount']>0 else -min(x,y)
            ok=(x>0)==op['zero'] and 0<filled<=abs(op['amount']) and (filled==abs(op['amount']) or v[2]==op['limit'])
            counts['log_direction_size_limit_match' if ok else 'log_mismatch']+=1
            if not ok:mismatches.append(tx['tx'])
        counts['unexplained_tracked_logs']+=len(remaining)
        p=prefixes[tx['tx']];counts['prefix_with_database_error']+=int(p['error'] is not None)
        for call in p['calls']:
            if call['to'] not in pools or not call['data'].startswith('0x128acb08'):continue
            raw=bytes.fromhex(call['data'][10:]);v=[int.from_bytes(raw[i:i+32],'big') for i in range(0,128,32)]
            expected=dict(pool=call['to'],zero=bool(v[1]),amount=signed(v[2]),limit=v[3])
            ok=any(all(op[k]==v for k,v in expected.items()) for op in ops)
            counts['bytecode_call_match' if ok else 'bytecode_call_mismatch']+=1
            if not ok:mismatches.append(tx['tx'])
        if len(fixtures)<3:
            fixtures.append(dict(tx=tx,expected=ops,tracked_pools=sorted(pools),prefix=p,
                caveat='subcalls are assumed successful; unrecorded pools omitted'))
    report=dict(counts=dict(counts),mismatches=mismatches,
                caveat='Retrospective sample. Prefix returns reverts to external calls; router may swallow failed subcalls. Numeric full-state parity is unproven.')
    Path('reports/amm/router29-multi-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    Path('tests/fixtures/router29_multi.json').write_text(json.dumps(fixtures,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if mismatches:raise SystemExit(1)
if __name__=='__main__':main()
