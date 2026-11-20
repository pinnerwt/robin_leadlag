"""Validate first V3 call arguments only; embedded settlement remains partial."""
import collections
import json
from pathlib import Path
from packed_routers import ROUTER_769, decode_packed
from v3_calldata import signed,word

def main():
    registry=json.load(open('config/optimistic-router-template.json'))
    prefix={r['tx']:r for r in map(json.loads,open('reports/amm/router769-prefix.jsonl'))}
    counts=collections.Counter();fixtures=[];mismatches=[]
    for row in map(json.loads,open('reports/amm/optimistic-target-corpus.jsonl')):
        tx=row['tx']
        if (tx['to'] or '').lower()!=ROUTER_769:continue
        op=decode_packed(ROUTER_769,tx['data'],registry)[0];p=prefix[tx['tx']]
        counts['transactions']+=1
        if p['error'] is not None or len(p['calls'])!=1:raise ValueError('unresolved prefix')
        call=p['calls'][0];raw=bytes.fromhex(call['data'][10:])
        expected=dict(pool=call['to'],zero=bool(word(raw,1)),amount=signed(word(raw,2)),limit=word(raw,3))
        ok=all(op[k]==v for k,v in expected.items());counts['bytecode_match' if ok else 'bytecode_mismatch']+=1
        if not ok:mismatches.append(tx['tx'])
        logs=[l for l in row['logs'] if l['address'].lower()==op['pool']]
        if len(logs)!=1:raise ValueError('ambiguous log validation')
        raw=bytes.fromhex(logs[0]['data'][2:]);x,y=signed(word(raw,0)),signed(word(raw,1));filled=max(x,y)
        ok=(x>0)==op['zero'] and 0<filled<=op['amount'] and (filled==op['amount'] or word(raw,2)==op['limit'])
        counts['log_direction_size_limit_match' if ok else 'log_mismatch']+=1
        if not ok:mismatches.append(tx['tx'])
        if not any(f['expected']['zero']==op['zero'] for f in fixtures):
            fixtures.append(dict(tx=tx,expected=expected,captured_call=call,coverage='first_swap_only_callback_unresolved'))
    report=dict(counts=dict(counts),mismatches=mismatches,caveat='Archived code/state, dummy pool accounts and ArbSys query interception. No callbacks or settlement executed; no whole-transaction coverage claim.')
    Path('reports/amm/router769-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    Path('tests/fixtures/router769.json').write_text(json.dumps(fixtures,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if mismatches:raise SystemExit(1)
if __name__=='__main__':main()
