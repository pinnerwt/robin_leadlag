"""Match pushed target-pool Swap logs to calldata decoding; never update prices."""
import argparse
import collections
import json
from amm_feed_state import ROUTERS, SWAP
from tape import records
from v3_calldata import decode

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('tape');ap.add_argument('--output',required=True);ap.add_argument('--research-registry',help='Retrospective new decoder profiles; not causal live coverage')
    a=ap.parse_args();extension=json.load(open(a.research_registry)) if a.research_registry else None;pools={};registry=None;started=False;transactions={};logs=[]
    for row in records([a.tape]):
        if row['kind']=='optimistic_checkpoint':
            pools={p['pool']:p for p in row['seed']['pools']};registry=row.get('registry')
            started=not row.get('initial')
            if extension and registry:
                registry=json.loads(json.dumps(registry))
                for address,profile in extension['routers'].items():
                    registry['routers'].setdefault(address,profile)
        elif row['kind']=='optimistic_input':
            event=row['event']
            if event['kind']=='feed_tx' and started:
                try:
                    ops=decode(event['to'],event['data'],pools,ROUTERS,packed_registry=registry)
                    touched=[o['pool'] for o in ops];reason=None;partial=any(o.get('coverage_note') for o in ops)
                except (ValueError,AttributeError) as exc:touched=[];reason=str(exc);partial=False
                transactions[event['tx']]=(event['to'],event['data'][:10],touched,reason,partial)
            if event['kind']=='chain_log':
                log=event['payload']
                if log['address'].lower() in pools and log.get('topics',[None])[0]==SWAP:
                    logs.append(log)
    counts=collections.Counter();routers=collections.Counter();seen=set()
    for log in logs:
        key=(log['transactionHash'],log.get('logIndex'))
        if key in seen:continue
        seen.add(key);counts['target_swap_logs']+=1
        tx=transactions.get(log['transactionHash'])
        if not tx:
            counts['no_post_sync_feed_transaction']+=1;continue
        to,selector,touched,reason,partial=tx
        covered=log['address'].lower() in touched
        counts['post_sync_swaps']+=1;counts['decoded_pool_intent' if covered else 'missing_pool_intent']+=1
        if covered and partial:counts['decoded_intent_with_unresolved_callback']+=1
        routers[(to,selector,covered,reason)]+=1
    report=dict(mode='retrospective_decoder_extensions' if extension else 'recorded_registry',counts=dict(counts),routers=[dict(to=k[0],selector=k[1],decoded_pool_intent=k[2],reason=k[3],swap_logs=v) for k,v in routers.most_common()],
                caveat='Intent coverage only, not numeric state parity or transaction success')
    open(a.output,'w').write(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(mode=report['mode'],counts=report['counts'],top_missing=[r for r in report['routers'] if not r['decoded_pool_intent']][:8]),indent=2))
if __name__=='__main__':main()
