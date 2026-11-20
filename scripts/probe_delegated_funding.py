"""Synthetic native take funding to expose subsequent delegated swap arguments."""
import json,subprocess,tempfile,argparse
from pathlib import Path
from probe_delegated_callback import push

def manager_code(callback,recipient):
 # Only the exact original unlock and take calls are executable in the inspector.
 head=b'\x5f\x35'+push(224)+b'\x1c'+push(0x0b0d9c09)+b'\x14\x61\x00\x00\x57'
 body=push(len(callback))+b'\x61\x00\x00'+push(0)+b'\x39'
 body+=push(0)+push(0)+push(len(callback))+push(0)+push(0)+bytes.fromhex('73'+recipient[2:])+b'\x5a\xf1\x50\x00'
 take=b'\x5b'+push(0)*4+push(68)+b'\x35'+push(36)+b'\x35\x5a\xf1\x50\x00'
 head=head[:-3]+(len(head)+len(body)).to_bytes(2,'big')+head[-1:]
 at=len(push(len(callback)))+1
 body=body[:at]+(len(head)+len(body)+len(take)).to_bytes(2,'big')+body[at+2:]
 return head+body+take+callback

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--balance',type=int);ap.add_argument('--output',type=int);ap.add_argument('--balance-delta',type=int);ap.add_argument('--second-output',type=int);ap.add_argument('--resume-getters');args=ap.parse_args()
 source=json.loads(Path('reports/amm/delegated-router-callback-sqrt-79228162514264337593543950336.json').read_text())
 case=next(c for c in source['cases'] if any(x['data'].startswith('0x0b0d9c09') for x in c['result']['calls']))
 tx=next(t for t in map(json.loads,Path('reports/amm/delegated-router-txs.jsonl').read_text().splitlines()) if t['tx']==case['tx'])
 prefix=next(r for r in map(json.loads,Path('reports/amm/delegated-router-getter-prefix.jsonl').read_text().splitlines()) if r['tx']==case['tx'])
 unlock=prefix['calls'][0];take=next(x for x in case['result']['calls'] if x['data'].startswith('0x0b0d9c09'))
 manager=take['to'];root=tx['to'].lower();seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
 seed['accounts'][manager]=dict(code='0x'+manager_code(bytes.fromhex(case['callback'][2:]),root).hex(),balance=hex(10**30),nonce='0x0',storage={})
 seed['getters']=case['synthetic_getters'];seed['trace_execution']=True
 seed['execute_targets']=[root];seed['execute_calls']=[manager+':'+unlock['data'],manager+':'+take['data']]
 if args.resume_getters:
  prior=json.loads(Path(args.resume_getters).read_text())
  assert prior['synthetic_v3_output']==args.output and prior['synthetic_second_output']==args.second_output and prior['synthetic_token_balance']==args.balance
  seed['getters']=prior['synthetic_getters']
 with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
  stages=[]
  for attempt in range(12 if args.second_output is not None else 8 if args.output is not None else 6 if args.balance is not None else 2):
   Path(tmp.name).write_text(json.dumps(seed))
   result=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx)+'\n',text=True));stages.append(result)
   deposits=[c for c in result['calls'] if c['to']=='0x0bd7d308f8e1639fab988df18a8011f41eacad73' and c['data']=='0xd0e30db0']
   added=False
   for c in deposits:
    entries=seed['getters'].setdefault(c['to'],{})
    if c['data'] not in entries:entries[c['data']]='0x';added=True
   if args.balance is not None:
    for c in result['calls']:
     if c['data'].startswith('0x70a08231') and len(c['data'])==74:
      entries=seed['getters'].setdefault(c['to'],{})
      if c['data'] not in entries:entries[c['data']]='0x'+args.balance.to_bytes(32,'big').hex();added=True
   if args.output is not None:
    for key,value in seed['getters'].get('0x4a0e65a3eccec6dbe60ae065f2e7bb85fae35eea',{}).items():
     if key.startswith('0x70a08231') and isinstance(value,str):
      seed['getters']['0x4a0e65a3eccec6dbe60ae065f2e7bb85fae35eea'][key]=[value,'0x'+(args.balance+(args.output if args.balance_delta is None else args.balance_delta)).to_bytes(32,'big').hex()]
    for c in result['calls']:
     if c['to']=='0xc3c9f0171490ef0f4536fe493f3b0ebb5ee0cb5e' and c['data'].startswith('0x128acb08'):
      d=bytes.fromhex(c['data'][10:]);amount=int.from_bytes(d[64:96],'big');assert int.from_bytes(d[32:64],'big')==1
      seed['getters'].setdefault(c['to'],{})[c['data']]='0x'+amount.to_bytes(32,'big').hex()+((-args.output)%(1<<256)).to_bytes(32,'big').hex();added=True
   if args.second_output is not None:
    token='0x5fc5360d0400a0fd4f2af552add042d716f1d168'
    for key,value in seed['getters'].get(token,{}).items():
     if key.startswith('0x70a08231') and isinstance(value,str):
      seed['getters'][token][key]=[value,'0x'+(args.balance+args.second_output).to_bytes(32,'big').hex()]
    for c in result['calls']:
     if c['to']=='0xc61284332117c3fb23a2a56cceffd07f7af60029' and c['data'].startswith('0x128acb08'):
      d=bytes.fromhex(c['data'][10:]);amount=int.from_bytes(d[64:96],'big');assert int.from_bytes(d[32:64],'big')==1
      seed['getters'].setdefault(c['to'],{})[c['data']]='0x'+amount.to_bytes(32,'big').hex()+((-args.second_output)%(1<<256)).to_bytes(32,'big').hex();added=True
   if args.second_output is not None:
    for c in result['calls']:
     reply=None
     if c['to']==manager and c['data']=='0xa5841194'+'0'*24+'5fc5360d0400a0fd4f2af552add042d716f1d168':reply='0x'
     if c['to']==manager and c['data']=='0x11da60b4':reply='0x'+args.second_output.to_bytes(32,'big').hex()
     if c['to']=='0x5fc5360d0400a0fd4f2af552add042d716f1d168' and c['data']=='0xa9059cbb'+'0'*24+manager[2:]+args.second_output.to_bytes(32,'big').hex():reply='0x'+(1).to_bytes(32,'big').hex()
     if reply is not None:
      entries=seed['getters'].setdefault(c['to'],{})
      if c['data'] not in entries:entries[c['data']]=reply;added=True
   if not added:break

 report=dict(synthetic_second_output=args.second_output,synthetic_balance_delta=args.balance_delta,synthetic_v3_output=args.output,synthetic_token_balance=args.balance,tx=tx,synthetic_manager_balance=10**30,synthetic_getters=seed['getters'],take=take,stages=stages,result=result,caveat='Synthetic funding and prices; actual delegated code. No historical swap or settlement parity claim.')
 Path('reports/amm/delegated-router-funded-'+('second-output-'+str(args.second_output) if args.second_output is not None else 'delta-'+str(args.balance_delta) if args.balance_delta is not None else 'output-'+str(args.output) if args.output is not None else 'probe' if args.balance is None else 'balance-'+str(args.balance))+'.json').write_text(json.dumps(report,indent=2)+'\n')
 print(result['error'],[(c['to'],c['data'][:10]) for c in result['calls']])
 print([(r['selector'],r['result'],r['output'][:70]) for r in result['execution_returns'] if r['selector'] in ('0x91dd7346','0x0b0d9c09')])
if __name__=='__main__':main()
