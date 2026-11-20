"""Offline compare fast parsers with actual deployed bytecode's first swap call.
Prefix execution deliberately stops before settlement: no success/state claim.
"""
import argparse,json
from collections import Counter
from pathlib import Path
from packed_routers import decode_packed,ROUTER_520,ROUTER_C33
p=argparse.ArgumentParser(description=__doc__);p.add_argument('corpus');p.add_argument('prefix');p.add_argument('--registry',default='config/packed-routers.json');p.add_argument('--output',default='reports/amm/router-decoder-parity.json');a=p.parse_args()
registry=json.load(open(a.registry));prefix={r['tx']:r for r in map(json.loads,open(a.prefix))};rows=list(map(json.loads,open(a.corpus)));split=int(len(rows)*.6);counts={};fixtures=[]
for i,row in enumerate(rows):
 tx=row['tx'];to=tx['to'].lower();selector=tx['data'][2:10]
 if (to,selector) not in ((ROUTER_520,'b2460c48'),(ROUTER_C33,'000000e7')):continue
 key=to+':'+selector;stats=counts.setdefault(key,{'train':Counter(),'heldout':Counter()})['train' if i<split else 'heldout']
 try:op=decode_packed(to,tx['data'],registry)[0]
 except ValueError:stats['unknown_registry']+=1;continue
 result=prefix[tx['tx']];calls=result['calls']
 if result['error'] or len(calls)!=1 or not calls[0]['data'].startswith('0x128acb08'):stats['prefix_unresolved']+=1;continue
 c=calls[0];raw=bytes.fromhex(c['data'][10:]);v=[int.from_bytes(raw[j:j+32],'big') for j in range(0,128,32)]
 expected=dict(pool=c['to'].lower(),zero=bool(v[1]),amount=v[2]-(1<<256) if v[2]>>255 else v[2],limit=v[3])
 if any(op[k]!=v for k,v in expected.items()):stats['mismatch']+=1;continue
 stats['exact_bytecode_call']+=1
 if sum(f['router']==to for f in fixtures)<3:fixtures.append(dict(router=to,calldata=tx['data'],expected=expected,tx=tx['tx']))
 swaps=[l for l in row['logs'] if l['topics'] and l['topics'][0]=='0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67']
 if len(swaps)!=1:stats['log_not_single_swap']+=1;continue
 log=swaps[0];raw=bytes.fromhex(log['data'][2:]);v=[int.from_bytes(raw[j:j+32],'big') for j in range(0,160,32)];x,y=[n-(1<<256) if n>>255 else n for n in v[:2]]
 filled=max(x,y) if op['amount']>0 else -min(x,y);partial=filled<abs(op['amount'])
 if log['address'].lower()!=op['pool'] or (x>0)!=op['zero'] or filled>abs(op['amount']) or (partial and v[2]!=op['limit']):stats['log_mismatch']+=1
 else:stats['log_direction_size_limit_match']+=1;stats['partial_fill']+=int(partial)
report=dict(corpus_count=len(rows),train_count=split,counts=counts,limitations=['event-bearing transactions only','prefix stopped before callback and settlement','historical router mapping snapshot, not continuous state reconstruction','logs validate direction, amount bound and partial-fill limit, not full swap math'])
Path(a.output).write_text(json.dumps(report,indent=2)+'\n');Path('tests/fixtures/packed_router_calls.json').write_text(json.dumps(fixtures,indent=2)+'\n');print(json.dumps(report,indent=2))
