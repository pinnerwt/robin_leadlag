"""Validate fixed parallel route amounts against captured logs and call traces."""
import collections
import json
from pathlib import Path
from packed_routers import decode_packed
from nested_routers import ROUTER_426
from v3_calldata import word,signed
from v3_state import MIN_SQRT,MAX_SQRT


def calls(node):
    yield node
    for child in node.get('calls',[]):yield from calls(child)


def main():
    registry=json.load(open('config/optimistic-router-template.json'))
    pools={p['pool']:p for p in json.load(open('captures/startup-v9-quotes.json'))['pools']}
    counts=collections.Counter();fixtures=[];mismatches=[]
    for row in map(json.loads,open('reports/amm/optimistic-target-corpus.jsonl')):
        tx=row['tx']
        if (tx['to'] or '').lower()!=ROUTER_426 or not tx['data'].startswith('0x32038e4b'):continue
        ops=decode_packed(ROUTER_426,tx['data'],registry,tracked_pools=pools)
        counts['transactions']+=1;counts['decoded_pool_operations']+=len(ops)
        remaining=list(row['logs'])
        for op in ops:
            log=next((l for l in remaining if l['address'].lower()==op['pool']),None)
            if log is None:counts['predicted_without_log']+=1;continue
            remaining.remove(log);raw=bytes.fromhex(log['data'][2:]);x,y=signed(word(raw,0)),signed(word(raw,1))
            ok=(x>0)==op['zero'] and max(x,y)==op['amount']
            counts['exact_log_direction_input_match' if ok else 'log_mismatch']+=1
            if not ok:mismatches.append(tx['tx'])
        counts['unexplained_tracked_logs']+=len(remaining)
        if not any(len(f['expected'])==len(ops) for f in fixtures):fixtures.append(dict(tx=tx,expected=ops,pools={a:dict(tokens=p['tokens'],fee=p['fee']) for a,p in pools.items()}))
    for record in json.load(open('reports/amm/router426-adapter-traces.json')):
        req=bytes.fromhex(record['request']['data'][10:]);tokenin=word(req,1);tokenout=word(req,3);amount=word(req,2)
        inner=req[word(req,5):];fee=word(inner,2) # bytes length, type=3, fee
        matching=[p for p in pools.values() if p['fee']==fee and set(map(lambda t:int(t,16),p['tokens']))=={tokenin,tokenout}]
        assert len(matching)==1
        swap=[c for c in calls(record['trace']) if c.get('input','').startswith('0x128acb08')]
        assert len(swap)==1
        raw=bytes.fromhex(swap[0]['input'][10:]);zero=tokenin<tokenout
        ok=(swap[0]['to']==matching[0]['pool'] and bool(word(raw,1))==zero and signed(word(raw,2))==amount
            and word(raw,3)==(MIN_SQRT+1 if zero else MAX_SQRT-1))
        counts['adapter_trace_argument_match' if ok else 'adapter_trace_mismatch']+=1
        if not ok:mismatches.append('adapter '+record['request']['data'])
    outer_path=Path('reports/amm/router426-outer-trace.json')
    if outer_path.exists():
        record=json.loads(outer_path.read_text());ops=decode_packed(ROUTER_426,record['request']['data'],registry,tracked_pools=pools)
        swap=[c for c in calls(record['trace']) if c.get('input','').startswith('0x128acb08')]
        counts['fresh_outer_swap_calls']=len(swap)
        for op,call in zip(ops,swap):
            raw=bytes.fromhex(call['input'][10:]);ok=(op['pool']==call['to'] and op['zero']==bool(word(raw,1)) and op['amount']==signed(word(raw,2)) and op['limit']==word(raw,3))
            counts['fresh_outer_argument_match' if ok else 'fresh_outer_argument_mismatch']+=1
            if not ok:mismatches.append('outer '+record['source_tx'])
    report=dict(counts=dict(counts),mismatches=mismatches,caveat='Real recorded Swap input amounts plus new-anchor read-only argument traces; not original historical full-state replay.')
    Path('reports/amm/router426-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    Path('tests/fixtures/router426.json').write_text(json.dumps(fixtures,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if mismatches or counts['predicted_without_log'] or counts['unexplained_tracked_logs']:raise SystemExit(1)
if __name__=='__main__':main()
