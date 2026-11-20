"""Continue actual kind-8 pool execution within the saved synthetic-funding harness."""
import argparse,json
from pathlib import Path
from probe_delegated_kind8 import run
from probe_delegated_funding import manager_code
from probe_delegated_callback import push

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--quote-output',type=int);ap.add_argument('--credit',action='store_true');args=ap.parse_args()
 evidence=json.loads(Path('reports/amm/delegated-kind8-funded-987654321-active.json').read_text())
 base=json.loads(Path('reports/amm/delegated-kind8-probe.json').read_text())
 tx=evidence['tx'];root=tx['to'].lower();unlock=base['prefix']['calls'][0];take=base['callback']['calls'][0];manager=unlock['to']
 s=json.loads(Path('captures/startup-v9-dependencies.json').read_text());s['trace_execution']=True;s['getters']=evidence['synthetic_getters']
 cb=bytes.fromhex('91dd7346'+unlock['data'][10:])
 s['accounts'][manager]=dict(code='0x'+manager_code(cb,root).hex(),balance=hex(10**30),nonce='0x0',storage={})
 lookup=json.loads(Path('reports/amm/delegated-single-prefix-probe.json').read_text())['cases'][0]['result']['calls'][0]
 calls=[unlock,take,lookup,evidence['result']['calls'][0],evidence['inner']['calls'][0],evidence['transfer_probe']['calls'][0]]
 s['execute_calls']=[c['to']+':'+c['data'] for c in calls];s['execute_targets']=[root]
 stages=[]
 for _ in range(12):
  r=run(s,tx);stages.append(r)
  print(r['error'],[(c['to'],c['scheme'],c['data'][:10]) for c in r['calls']],flush=True)
  if r['error'] or len(r['calls'])!=1:break
  c=r['calls'][0];key=c['to']+':'+c['data']
  # Extend only observed read-only dependencies with saved code/state.
  if c['scheme']!='StaticCall' or c['to'] not in s['accounts'] or key in s['execute_calls']:break
  s['execute_calls'].append(key)
 quoted=None;after_transfer=None;credited=None;withdrawn=None;settled=None;terminal=None
 if args.quote_output is not None:
  c=stages[0]['calls'][0];key=c['to']+':'+c['data'];s['execute_calls'].remove(key)
  s['getters'].setdefault(c['to'],{})[c['data']]='0x'+args.quote_output.to_bytes(32,'big').hex()
  quoted=run(s,tx)
  print('synthetic quote',quoted['error'],[(c['to'],c['data'][:10]) for c in quoted['calls']],flush=True)
  calls=quoted['calls']
  if len(calls)==1 and calls[0]['to']=='0x0bd7d308f8e1639fab988df18a8011f41eacad73' and calls[0]['data'].startswith('0xa9059cbb'):
   c=calls[0];s['getters'].setdefault(c['to'],{})[c['data']]='0x'+(1).to_bytes(32,'big').hex()
   after_transfer=run(s,tx)
   print('after synthetic transfer',after_transfer['error'],[(c['to'],c['data'][:10]) for c in after_transfer['calls']],flush=True)
   if args.credit:
    token=c['to'];balance='0x70a08231'+'00'*12+root[2:];word='0x'+args.quote_output.to_bytes(32,'big').hex()
    s['getters'][token][balance]=['0x'+'00'*32,'0x'+'00'*32,word,word]
    credited=run(s,tx)
    print('credited',credited['error'],[(c['to'],c['data'][:10]) for c in credited['calls']],flush=True)
    calls=credited['calls']
    if len(calls)==1 and calls[0]['to']==token and calls[0]['data'].startswith('0x2e1a7d4d'):
     withdrawal=calls[0]
     # Synthetic WETH withdrawal sends the requested native value to CALLER.
     code=push(0)*4+push(4)+b'\x35\x33\x5a\xf1\x50\x00'
     s['accounts'][token]=dict(code='0x'+code.hex(),balance=hex(10**30),nonce='0x0',storage={})
     s['execute_calls'].append(token+':'+withdrawal['data'])
     withdrawn=run(s,tx)
     print('withdrawn',withdrawn['error'],[(c['to'],c['data'][:10]) for c in withdrawn['calls']],flush=True)
     calls=withdrawn['calls']
     if len(calls)==1 and calls[0]['to']==manager and calls[0]['data']=='0x11da60b4':
      s['getters'].setdefault(manager,{})['0x11da60b4']='0x'+args.quote_output.to_bytes(32,'big').hex()
      settled=run(s,tx)
      print('settled',settled['error'],[(c['to'],c['data'][:10]) for c in settled['calls']],flush=True)
      terminal=settled;take_stages=[]
      for _ in range(4):
       calls=terminal['calls']
       if len(calls)!=1 or calls[0]['to']!=manager or not calls[0]['data'].startswith('0x0b0d9c09'):break
       c=calls[0];s['getters'].setdefault(manager,{})[c['data']]='0x'
       terminal=run(s,tx);take_stages.append(terminal)
       print('take continuation',terminal['error'],[(c['to'],c['data'][:10]) for c in terminal['calls']],flush=True)
 Path('reports/amm/delegated-kind8-pool-'+('probe' if args.quote_output is None else 'quote-'+str(args.quote_output))+('-credited' if args.credit else '')+'.json').write_text(json.dumps(dict(terminal=terminal,take_stages=take_stages if terminal is not None else [],synthetic_take_returns=True if terminal is not None else False,settled=settled,withdrawn=withdrawn,credited=credited,synthetic_credit=args.credit,after_transfer=after_transfer,synthetic_quote_output=args.quote_output,quoted=quoted,tx=tx,stages=stages,result=r,execute_calls=s['execute_calls'],
  caveat='Actual pool prefix within synthetic funding/full credit/active gate/transfer harness. Read-only dependencies execute saved state; no historical success claim.'),indent=2)+'\n')
if __name__=='__main__':main()
