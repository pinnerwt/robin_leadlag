"""Offline extension evidence: bytecode-prefix arguments and independent Swap logs.
Prefix experiments use archived router state and stub pool getters/accounts.
They establish call encoding, not historical execution success or continuous state.
"""
import collections
import json
from pathlib import Path
from packed_routers import decode_packed, ROUTER_9E, ROUTER_278, ROUTER_29
from v3_calldata import signed


def main():
    registry=json.load(open('config/optimistic-router-template.json'))
    rows=[r for r in map(json.loads,open('reports/amm/optimistic-target-corpus.jsonl'))
          if (r['tx']['to'] or '').lower() in (ROUTER_9E,ROUTER_278,ROUTER_29)]
    prefix={r['tx']:r for path in ['reports/amm/new-router-prefix.jsonl','reports/amm/router29-current-prefix.jsonl']
            for r in map(json.loads,open(path))}
    stats={};fixtures=[];mismatches=[]
    split=int(len(rows)*.6)
    for i,row in enumerate(rows):
        tx=row['tx'];router=tx['to'].lower();group='train' if i<split else 'heldout'
        counter=stats.setdefault(router,{}).setdefault(group,collections.Counter())
        try:
            if tx['data'].startswith('0x164cb8f5'):raise ValueError('validated separately')
            ops=decode_packed(router,tx['data'],registry)
        except ValueError as exc:
            counter['unsupported']+=1;continue
        counter['decoded']+=1
        p=prefix.get(tx['tx']);op=ops[0]
        if p and p['error'] is None and len(p['calls'])==1 and p['calls'][0]['data'].startswith('0x128acb08'):
            call=p['calls'][0];raw=bytes.fromhex(call['data'][10:])
            v=[int.from_bytes(raw[j:j+32],'big') for j in range(0,128,32)]
            expected=dict(pool=call['to'],zero=bool(v[1]),amount=signed(v[2]),limit=v[3])
            matched=all(op[k]==v for k,v in expected.items());counter['bytecode_match' if matched else 'bytecode_mismatch']+=1
            if not matched:mismatches.append(tx['tx'])
            if not any(f['router']==router and f['expected']['zero']==op['zero'] and (f['expected']['amount']<0)==(op['amount']<0) for f in fixtures):
                fixtures.append(dict(router=router,calldata=tx['data'],expected=expected,tx=tx['tx'],captured_call=call,
                    evidence='archived_router_prefix_with_stubbed_pool_getter_not_historical_execution'))
        else:counter['prefix_unresolved']+=1
        matches=[l for l in row['logs'] if l['address'].lower()==op['pool']]
        if len(matches)!=1:
            counter['log_not_single_matching_pool']+=1;continue
        log=matches[0];raw=bytes.fromhex(log['data'][2:]);v=[int.from_bytes(raw[j:j+32],'big') for j in range(0,160,32)]
        x,y=signed(v[0]),signed(v[1]);filled=max(x,y) if op['amount']>0 else -min(x,y)
        partial=filled<abs(op['amount'])
        ok=(x>0)==op['zero'] and 0<filled<=abs(op['amount']) and (not partial or v[2]==op['limit'])
        counter['log_direction_size_limit_match' if ok else 'log_mismatch']+=1
        if not ok:mismatches.append(tx['tx'])
    report=dict(stats=stats,split_index=split,total_selected_transactions=len(rows),mismatches=mismatches,
        caveats=['retrospective decoder research, not causal registry availability',
                 'chronological diagnostic split; decoders were developed with access to this corpus',
                 'stubbed getter/account prefix experiments do not prove historical execution',
                 'logs validate direction, amount bound and partial limit, not final state parity'])
    Path('reports/amm/router-extensions-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    Path('tests/fixtures/router_extensions.json').write_text(json.dumps(fixtures,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if mismatches:raise SystemExit(1)

if __name__=='__main__':main()
