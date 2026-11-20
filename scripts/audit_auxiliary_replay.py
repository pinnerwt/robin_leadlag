"""Validate auxiliary calldata storage advances against pushed FeedUpdated events."""
import json,subprocess
from pathlib import Path
B=Path('reports/ohio-20ms-backtest');seed=json.load(open(B/'ETHUSDT-seed.json'));anchor=int(seed['anchor']['number'],16)
receipts=json.load(open(B/'auxiliary-receipts.json'))
p=subprocess.Popen(['target/release/examples/spcx_state_worker',str(B/'ETHUSDT-seed.json'),'--provider-full'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
errors=[];count=0;updates=0
rows=[json.loads(l) for l in open(B/'ETHUSDT-events.jsonl')];rows=[r for r in rows if r['kind']=='aux_oracle' and r.get('block_number') and int(r['block_number'],16)>anchor];rows.sort(key=lambda r:(int(r['block_number'],16),int(r.get('transaction_index','0x0'),16)))
for r in rows:
 p.stdin.write(json.dumps(r)+'\n');p.stdin.flush();out=json.loads(p.stdout.readline())
 if 'error' in out:errors.append(dict(tx=r['tx'],error=out['error']));continue
 actual=set(out['result']['updated_feeds']);expected={int(x['feed'],16) for x in receipts.get(r['tx'],[])};tracked={x['feed'] for x in out['result']['tracked']};expected&=tracked
 if actual!=expected:errors.append(dict(tx=r['tx'],calldata_updated=sorted(actual),log_updated=sorted(expected)))
 count+=1;updates+=len(actual)
p.stdin.close();p.wait()
result=dict(transactions=count,updated_tracked_feeds=updates,mismatches=errors,validation='Calldata reducer vs receipt event IDs; logs only validate and never choose decision updates. Signature acceptance is assumed at decision time.')
(B/'auxiliary-acceptance-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(result if len(errors)<5 else {**result,'mismatches':len(errors)})
