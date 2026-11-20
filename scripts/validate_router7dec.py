"""Verify packed memory-copy arguments, without executing pool settlement."""
import collections
import json
from pathlib import Path
from packed_routers import ROUTER_7DEC,decode_packed
from v3_calldata import signed,word

def main():
    registry=json.load(open('config/optimistic-router-template.json'))
    prefixes={r['tx']:r for r in map(json.loads,open('reports/amm/router7dec-prefix.jsonl'))}
    counts=collections.Counter();mismatches=[];fixtures=[]
    for row in map(json.loads,open('reports/amm/optimistic-target-corpus.jsonl')):
        tx=row['tx']
        if (tx['to'] or '').lower()!=ROUTER_7DEC:continue
        op=decode_packed(ROUTER_7DEC,tx['data'],registry)[0];p=prefixes[tx['tx']]
        assert p['error'] is None and len(p['calls'])==1
        call=p['calls'][0];raw=bytes.fromhex(call['data'][10:])
        expected=dict(pool=call['to'],zero=bool(word(raw,1)),amount=signed(word(raw,2)),limit=word(raw,3))
        ok=all(op[k]==v for k,v in expected.items());counts['bytecode_match' if ok else 'bytecode_mismatch']+=1
        if not ok:mismatches.append(tx['tx'])
        logs=[l for l in row['logs'] if l['address'].lower()==op['pool']];assert len(logs)==1
        raw=bytes.fromhex(logs[0]['data'][2:]);x,y=signed(word(raw,0)),signed(word(raw,1))
        filled=max(x,y) if op['amount']>0 else -min(x,y)
        ok=(x>0)==op['zero'] and 0<filled<=abs(op['amount']) and (filled==abs(op['amount']) or word(raw,2)==op['limit'])
        counts['log_direction_size_limit_match' if ok else 'log_mismatch']+=1
        if not ok:mismatches.append(tx['tx'])
        payload=bytes.fromhex(tx['data'][2:]);key=(payload[0],payload[44]>>7)
        if not any(tuple(f['case'])==key for f in fixtures):fixtures.append(dict(case=key,tx=tx,expected=expected,captured_call=call))
    report=dict(counts=dict(counts),mismatches=mismatches,caveat='Archived router bytecode/state with dummy pool accounts. Argument and log-bound parity, not continuous-state proof.')
    Path('reports/amm/router7dec-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    Path('tests/fixtures/router7dec.json').write_text(json.dumps(fixtures,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if mismatches:raise SystemExit(1)
if __name__=='__main__':main()
