"""Bounded startup-only proof collection. Completeness requires verified trie closure."""
import argparse,json,subprocess
from pathlib import Path
from bootstrap_state import Bootstrap
from audit_storage_trie import audit
p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--max-probes',type=int,default=512);p.add_argument('--fresh',action='store_true');p.add_argument('--probe-start',type=int);p.add_argument('--hash-budget',type=int,default=10000000);p.add_argument('--reuse-identical-root',action='store_true',help='Verify each new block account proof and require the original storage root before reusing content-addressed nodes');a=p.parse_args()
d=json.loads(a.input.read_text());b=Bootstrap('https://rpc-robinhood.blockmachine.io',interval=.7);used=0;counter=a.probe_start if a.probe_start is not None else d.get('probe_counter',16)
if a.fresh:
 address=d['proof']['address'];head=b.rpc('eth_getBlockByNumber',['latest',False])
 d=dict(anchor=head,proof=b.rpc('eth_getProof',[address,[hex(i) for i in range(16)],head['number']]))
while True:
 r=audit(d);r.update(additional_probes=used,rpc_calls=b.calls);a.report.write_text(json.dumps(r,indent=2)+'\n');a.output.write_text(json.dumps(d,separators=(',',':'))+'\n')
 print('leaves',len(r['hashed_storage']),'missing',len(r['missing_nodes']),'probes',used,'complete',r['complete'],flush=True)
 if r['complete'] or used>=a.max_probes:break
 prefixes=[n['prefix'] for n in r['missing_nodes']][:a.max_probes-used]
 plan=json.loads(subprocess.check_output(['target/release/examples/proof_probe_keys'],input=json.dumps(dict(prefixes=prefixes,start=counter,limit=a.hash_budget)).encode()));counter=plan['next_counter'];keys=list(dict.fromkeys(x['key'] for x in plan['found']))
 d['probe_counter']=counter;a.output.write_text(json.dumps(d,separators=(',',':'))+'\n')
 if not keys:raise RuntimeError('probe preimage budget exhausted')
 for start in range(0,len(keys),64):
  batch=keys[start:start+64];head=b.rpc('eth_getBlockByNumber',['latest',False]) if a.reuse_identical_root else d['anchor']
  v=b.rpc('eth_getProof',[d['proof']['address'],batch,head['number']])
  if v['storageHash']!=d['proof']['storageHash']:raise ValueError('storage root changed; cannot combine states')
  if a.reuse_identical_root:
   check=audit(dict(anchor=head,proof=v))
   if not check['account_root_verified']:raise ValueError('new anchor account proof invalid')
   d.setdefault('identical_root_sources',[]).append(dict(anchor=head,accountProof=v['accountProof'],storageHash=v['storageHash']))
  elif v['accountProof']!=d['proof']['accountProof']:raise ValueError('fixed-anchor proof disagreement')
  if len(v['storageProof'])!=len(batch):raise ValueError('proof count mismatch')
  d['proof']['storageProof'].extend(v['storageProof']);used+=len(batch)
  a.output.write_text(json.dumps(d,separators=(',',':'))+'\n')
