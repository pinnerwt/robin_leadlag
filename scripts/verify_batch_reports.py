"""Offline comparison of report storage and native payments with chain witnesses."""
import argparse,json,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('fixtures',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
cases=json.loads(a.fixtures.read_text());cases=cases if isinstance(cases,list) else [cases];results=[]
for f in cases:
 with tempfile.NamedTemporaryFile(mode='w') as file:
  json.dump(f,file);file.flush();proc=subprocess.run(['target/release/examples/arbos_report',file.name],text=True,capture_output=True)
 local=json.loads(proc.stdout) if proc.returncode==0 else {};diff=f['diff'][1]['result']
 expected={address:{hex(int(k,16)):hex(int(v,16)) for k,v in account['storage'].items()} for address,account in diff['post'].items() if account.get('storage')}
 for address,account in diff['pre'].items():
  for key in account.get('storage',{}):
   if key not in diff['post'].get(address,{}).get('storage',{}):expected.setdefault(address,{})[hex(int(key,16))]='0x0'
 balances={address:hex(int(account['balance'],16)) for address,account in diff['post'].items() if 'balance' in account}
 results.append(dict(sequence=f['message']['sequence'],storage_matched=local.get('writes')==expected,balances_matched=local.get('balances')==balances,error=proc.stderr if proc.returncode else None,local=local,expected={'writes':expected,'balances':balances}))
a.output.write_text(json.dumps(results,indent=2)+'\n');print([(r['sequence'],r['storage_matched'],r['balances_matched']) for r in results])
if not all(r['storage_matched'] and r['balances_matched'] for r in results):raise SystemExit('report parity failed')
