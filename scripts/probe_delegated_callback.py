"""Synthetic manager unlock callback; only downstream argument evidence, not settlement."""
import json,subprocess,tempfile,copy,argparse
from pathlib import Path

def push(n):
 b=n.to_bytes(max(1,(n.bit_length()+7)//8),'big');return bytes([0x5f+len(b)])+b

def callback_code(data,recipient):
 code=push(len(data))+b'\x61\x00\x00'+push(0)+b'\x39'
 code+=push(0)+push(0)+push(len(data))+push(0)+push(0)+bytes.fromhex('73'+recipient[2:])+b'\x5a\xf1\x50\x00'
 at=len(push(len(data)))+1
 return code[:at]+len(code).to_bytes(2,'big')+code[at+2:]+data

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--sqrt',type=int);args=ap.parse_args()
 prior=json.loads(Path('reports/amm/delegated-router-callback-probe.json').read_text()) if args.sqrt is not None else None
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
 txs={t['tx']:t for t in map(json.loads,Path('reports/amm/delegated-router-txs.jsonl').read_text().splitlines())}
 cases=[]
 for prefix in map(json.loads,Path('reports/amm/delegated-router-getter-prefix.jsonl').read_text().splitlines()):
  if len(prefix['calls'])!=1:continue
  call=prefix['calls'][0]
  if call['data'][:10]!='0x48c89491':continue
  root=call['caller'].lower();manager=call['to'];tx=txs[prefix['tx']]
  cb=bytes.fromhex('91dd7346'+call['data'][10:])
  s=copy.deepcopy(seed);s['trace_execution']=True
  s['accounts'][manager]=dict(code='0x'+callback_code(cb,root).hex(),balance='0x0',nonce='0x0',storage={})
  s['execute_calls']=[manager+':'+call['data']]
  s['execute_targets']=[root]
  if prior is not None:
   previous=next(c for c in prior['cases'] if c['tx']==tx['tx'])
   s['getters']={c['to']:{'0x3850c7bd':'0x'+args.sqrt.to_bytes(32,'big').hex()} for c in previous['result']['calls'] if c['data']=='0x3850c7bd'}
  for p in json.loads(Path('captures/startup-v9-quotes.json').read_text())['pools']:
   for selector,token in zip(('0x0dfe1681','0xd21220a7'),p['tokens']):
    s.setdefault('getters',{}).setdefault(p['pool'],{})[selector]='0x'+int(token,16).to_bytes(32,'big').hex()
  with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
   stages=[]
   for attempt in range(4 if args.sqrt is not None else 1):
    Path(tmp.name).write_text(json.dumps(s))
    result=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx)+'\n',text=True));stages.append(result)
    added=False
    if args.sqrt is not None:
     for c in result['calls']:
      if c['data']=='0x3850c7bd' or (c['data'].startswith('0x1e2eaeaf') and len(c['data'])==74):
       entries=s.setdefault('getters',{}).setdefault(c['to'],{})
       if c['data'] not in entries:entries[c['data']]='0x'+args.sqrt.to_bytes(32,'big').hex();added=True
    if not added:break
  cases.append(dict(tx=tx['tx'],callback='0x'+cb.hex(),stages=stages,synthetic_getters=s.get('getters',{}),result=result))
  print(tx['tx'][:12],result['error'],[(c['to'],c['data'][:10]) for c in result['calls']])
 Path('reports/amm/delegated-router-callback-'+('probe' if args.sqrt is None else 'sqrt-'+str(args.sqrt))+'.json').write_text(json.dumps(dict(synthetic_sqrt=args.sqrt,caveat='Synthetic manager callback; ignores callback result. No real pool execution or root success claim.',cases=cases),indent=2)+'\n')
if __name__=='__main__':main()
