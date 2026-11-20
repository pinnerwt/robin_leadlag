"""Single-field hook fee interventions, explicitly synthetic and offline."""
import copy,json
from pathlib import Path
from probe_delegated_kind8 import run
SLOT='0xe18381f46b2c53f0e43ad1952216bbe3fb27345d4b2a467118dab1a305caa6f9'
def main():
 full=json.loads(Path('captures/startup-v9-dependencies.json').read_text());base=json.loads(Path('reports/amm/delegated-settler-hook.json').read_text())['cases'][1];tx=base['tx'];hook=tx['to']
 seed=dict(anchor=full['anchor'],trace_execution=True,accounts={a:v for a,v in full['accounts'].items() if a in (hook,tx['from'],'0x'+'00'*20)})
 original=int(seed['accounts'][hook]['storage'][SLOT],16);rows=[]
 for shift in (None,160,176,192,208,224):
  s=copy.deepcopy(seed);value=original if shift is None else (original&~(65535<<shift))|(1<<shift)
  s['accounts'][hook]['storage'][SLOT]=hex(value);r=run(s,tx)
  rows.append(dict(shift=shift,synthetic_value=hex(value),result=r));print(shift,r['error'],[(c['data'][:10],int(c['data'][-64:],16)) for c in r['calls']],flush=True)
 rounding=[]
 for output in (36,55,99,101,10001,820349038648306):
  changed=copy.deepcopy(tx);raw=bytearray.fromhex(tx['data'][2:]);old=int.from_bytes(raw[292:324],'big');delta=(output<<128)|(old&((1<<128)-1));raw[292:324]=delta.to_bytes(32,'big');changed['data']='0x'+raw.hex()
  r=run(seed,changed);rounding.append(dict(output=output,result=r))
  print('rounding',output,r['error'],r['output'],[(c['data'][:10],int(c['data'][-64:],16)) for c in r['calls']],flush=True)
 Path('reports/amm/delegated-hook-fee-fields.json').write_text(json.dumps(dict(tx=tx,slot=SLOT,original=hex(original),cases=rows,rounding=rounding,caveat='One uint16 changed to1 per synthetic counterfactual. Baseline checkpoint retained. Take intercepted; no state committed.'),indent=2)+'\n')
if __name__=='__main__':main()
