"""Calldata interventions against original delegated bytecode, before unlock."""
import json,subprocess
from pathlib import Path
source=json.loads(Path('reports/amm/delegated-router-funded-balance-0.json').read_text())['tx']
raw=bytes.fromhex(source['data'][2:]);assert raw[:6].hex()=='0c89e77a0608'
cases=[]
for amount in (1,10**18,(1<<64)-1):
 b=bytearray(raw);b[185:193]=amount.to_bytes(8,'big')
 cases.append(dict(kind='first_amount',value=amount,tx=dict(source,data='0x'+b.hex())))
for index in (1,3):
 b=bytearray(raw);replacement='11'*20;b[6+20*index:26+20*index]=bytes.fromhex(replacement)
 cases.append(dict(kind='address_table',value=index,replacement='0x'+replacement,tx=dict(source,data='0x'+b.hex())))
result=subprocess.check_output(['target/release/examples/router_prefix','captures/startup-v9-dependencies.json'],input=''.join(json.dumps(c['tx'])+'\n' for c in cases),text=True)
for c,line in zip(cases,result.splitlines()):
 r=json.loads(line);c['result']=r
 assert r['error'] is None and len(r['calls'])==1 and r['calls'][0]['data'].startswith('0x48c89491')
 d=bytes.fromhex(r['calls'][0]['data'][10:]);print(c['kind'],c['value'],int.from_bytes(d[320:352],'big'))
 if c['kind']=='first_amount':assert int.from_bytes(d[320:352],'big')==c['value']
 else:
  # First and second V3 route pools in the expanded first strategy.
  off=896 if c['value']==1 else 1280
  print('replacement words',[i for i in range(0,len(d),32) if d[i:i+32]==bytes.fromhex('00'*12+'11'*20)])
Path('reports/amm/delegated-encoding-probe.json').write_text(json.dumps(dict(cases=cases,caveat='Controlled compressed calldata mutations; prefix before manager unlock, not successful route execution.'),indent=2)+'\n')
