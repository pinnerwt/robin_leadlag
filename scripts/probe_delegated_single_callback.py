"""Execute saved single-route router callbacks with explicit synthetic manager/getters."""
import copy,json,subprocess,tempfile
from pathlib import Path
from probe_delegated_callback import callback_code

def main():
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());cases=[]
 for prior in json.loads(Path('reports/amm/delegated-single-prefix-probe.json').read_text())['cases']:
  calls=[c for c in prior['result']['calls'] if c['data'].startswith('0x48c89491')]
  if len(calls)!=1:continue
  call=calls[0];root=call['caller'].lower();manager=call['to'];s=copy.deepcopy(seed)
  s['trace_execution']=True;s['getters']=prior['synthetic_getters']
  for a in prior['synthetic_accounts']:s['accounts'][a]=dict(code='0x00',balance='0x0',nonce='0x0',storage={})
  cb=bytes.fromhex('91dd7346'+call['data'][10:])
  s['accounts'][manager]=dict(code='0x'+callback_code(cb,root).hex(),balance='0x0',nonce='0x0',storage={})
  s['execute_calls']=[manager+':'+call['data']];s['execute_targets']=[root]
  for action in prior['plan']['actions']:
   for token in (action['token_in'],action['token_out']):
    s['getters'].setdefault(token,{})['0x70a08231'+'00'*12+root[2:]]='0x'+'00'*32
  with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
   Path(tmp.name).write_text(json.dumps(s))
   result=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(prior['tx'])+'\n',text=True))
  stages=[result]
  takes=[c for c in result['calls'] if c['to']==manager and c['data'].startswith('0x0b0d9c09')]
  if takes:
   for take in takes:
    s['getters'].setdefault(manager,{})[take['data']]='0x'
    token=prior['plan']['actions'][0]['token_in']
    s['getters'][token]['0x70a08231'+'00'*12+root[2:]]=['0x'+'00'*32,'0x'+prior['plan']['header'][3].to_bytes(32,'big').hex()]
   with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
    Path(tmp.name).write_text(json.dumps(s))
    result=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(prior['tx'])+'\n',text=True))
   stages.append(result)
  cases.append(dict(tx=prior['tx'],plan=prior['plan'],synthetic_getters=s['getters'],stages=stages,result=result))
  print(prior['tx']['tx'][:12],result['error'],[(c['to'],c['data'][:10]) for c in result['calls']],flush=True)
 Path('reports/amm/delegated-single-callback-probe.json').write_text(json.dumps(dict(cases=cases,caveat='Synthetic manager callback ignores callback failure; synthetic metadata/condition getters inherited from prefix probe. All token balance reads are synthetic zero; manager take is stubbed successful with synthetic input-token balance credit. Argument evidence only.'),indent=2)+'\n')
if __name__=='__main__':main()
