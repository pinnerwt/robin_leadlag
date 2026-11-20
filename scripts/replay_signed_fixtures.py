"""Offline independent historical execution parity, not continuous state replay."""
import argparse,json,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fixtures',default='captures/signed-router-fixtures.json');p.add_argument('--output',default='reports/amm/signed-router-parity.json');a=p.parse_args();out=[]
for f in json.load(open(a.fixtures)):
 f['tx']['block_base_fee']=f['header']['baseFeePerGas']
 for addr,info in f['fee_account_witness']['before'].items():f['accounts'][addr]=dict(info,balance='0x'+info['balance'])
 with tempfile.NamedTemporaryFile(mode='w') as seed:
  json.dump({'accounts':f['accounts']},seed);seed.flush()
  p=subprocess.run(['target/release/examples/router_execute',seed.name,'--units-mode=signed'],input=json.dumps(f['tx'])+'\n',text=True,capture_output=True)
  if p.returncode:out.append(dict(tx=f['tx']['tx'],error=p.stderr));print(p.stderr);continue
  r=json.loads(p.stdout);diff=f['diff'];expected={};balance_mismatch=[]
  for addr,info in f['fee_account_witness']['after'].items():
   diff['post'][addr]=dict(info,balance='0x'+info['balance'])
  for addr,account in diff['post'].items():
   if account.get('storage'):expected[addr.lower()]={hex(int(k,16)):hex(int(v,16)) for k,v in account['storage'].items()}
   for key in ('balance','nonce'):
    if key in account:
     got=r['accounts'].get(addr.lower(),{}).get(key);want=account[key]
     if key=='balance':want=hex(int(want,16))
     if got!=want:balance_mismatch.append(dict(address=addr,key=key,expected=want,actual=got))
  for addr,account in diff['pre'].items():
   for slot in account.get('storage',{}):
    if slot not in diff['post'].get(addr,{}).get('storage',{}):expected.setdefault(addr.lower(),{})[hex(int(slot,16))]='0x0'
  norm=lambda logs:[dict(address=x['address'].lower(),topics=x['topics'],data=x['data']) for x in logs]
  logs_matched=norm(r['logs'])==norm(f['receipt']['logs'])
  success_matched=r['success']==(int(f['receipt']['status'],16)==1)
  row=dict(logs_matched=logs_matched,success_matched=success_matched,tx=f['tx']['tx'],router=f['tx']['to'],error=r['error'],success=r['success'],gas_local=r['gas_used'],gas_chain=int(f['receipt']['gasUsed'],16),balance_mismatch=balance_mismatch,storage_matched=expected==r['changed_storage'],expected_storage=expected,local=r)
  out.append(row);print(json.dumps({k:v for k,v in row.items() if k not in ('local','expected_storage')}))
Path(a.output).write_text(json.dumps(out,indent=2)+'\n')

if not out or any(r.get("error") or not r.get("storage_matched") or not r.get("logs_matched") or not r.get("success_matched") or r.get("balance_mismatch") or r.get("gas_local")!=r.get("gas_chain") for r in out):raise SystemExit("signed execution parity failed")
