"""Offline prefix argument probe with synthetic slot0. Not historical state replay."""
import json,subprocess,copy
s=json.load(open('captures/startup-v9-dependencies.json'));a='0x61083b541a5851d373cf01c22dde3946d14a0525'
s['trace_execution']=True
s['accounts']={a:s['accounts'][a], '0x'+'00'*20:dict(code='0x',balance='0x0',nonce='0x0',storage={})}
rows=[json.loads(l)['tx'] for l in open('reports/amm/optimistic-target-corpus.jsonl') if (json.loads(l)['tx']['to'] or '').lower()==a]
out=[]
for t in rows:
 raw=bytes.fromhex(t['data'][2:]);limit=int.from_bytes(raw[19:39],'big');zero=bool(raw[2]&1);pool='0x'+raw[39:59].hex()
 s['accounts'][pool]={'code':'0x00','balance':'0x0','nonce':'0x0','storage':{}}
 s['accounts'][t['from'].lower()]={'code':'0x','balance':'0xffffffffffffffffffff','nonce':hex(t['nonce']),'storage':{}}
 s['getters']={pool:{'0x3850c7bd':'0x'+(limit+1 if zero else limit-1).to_bytes(32,'big').hex()}}
 open('/tmp/router610seed.json','w').write(json.dumps(s))
 r=json.loads(subprocess.check_output(['target/release/examples/router_prefix','/tmp/router610seed.json'],input=json.dumps(t)+'\n',text=True))
 assert not r['error'] and len(r['calls'])==1 and r['calls'][0]['data'].startswith('0x128acb08'),r
 print(t['tx'],len(raw),raw[2],r['error'],[(c['to'],c['data'][:10]) for c in r['calls']])
 out.append(dict(tx=t,result=r))
open('reports/amm/router610-prefix.json','w').write(json.dumps(out,indent=2)+'\n')
