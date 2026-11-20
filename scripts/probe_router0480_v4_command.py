"""Isolated opcode06 and real root unlock callback with synthetic manager harness."""
import argparse,copy,json
from pathlib import Path
from probe_delegated_kind8 import run
from probe_delegated_callback import callback_code
from router0480_first_swap import ROUTER

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=int);ap.add_argument('--settle',action='store_true');args=ap.parse_args()
 base=json.loads(Path('captures/startup-v9-dependencies.json').read_text());rows=[]
 for prefix in ('0xac088a83af','0x0b7ab3b8f6'):
  original=next(json.loads(l)['tx'] for l in Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines() if json.loads(l)['tx']['tx'].startswith(prefix));raw=bytearray.fromhex(original['data'][2:]);offsets=[int.from_bytes(raw[2+2*i:4+2*i],'big') for i in range(raw[0])];index=next(i for i,o in enumerate(offsets) if raw[o]==6);offset=offsets[index];raw[0]=2;raw[1]=0;raw[2:6]=offset.to_bytes(2,'big')+offsets[-1].to_bytes(2,'big');tx=dict(original,data='0x'+raw.hex());keep={ROUTER,tx['from'].lower(),'0x'+'00'*20};s=copy.deepcopy(base);s['accounts']={a:v for a,v in s['accounts'].items() if a in keep or a[2:] in tx['data'].lower()};s.update(trace_execution=True,getters={});stages=[];mocks=[]
  for _ in range(12):
   r=run(s,tx);stages.append(r)
   if r['error'] or len(r['calls'])!=1:break
   c=r['calls'][0]
   if c['data'].startswith('0x70a08231'):
    s['getters'].setdefault(c['to'],{})[c['data']]='0x'+bytes(32).hex();mocks.append(c);continue
   if c['data'].startswith('0x48c89491'):
    cb=bytes.fromhex('91dd7346'+c['data'][10:]);s['accounts'][c['to']]['code']='0x'+callback_code(cb,ROUTER).hex();s['execute_calls']=[c['to']+':'+c['data']];s['execute_targets']=[ROUTER];continue
   if args.output is not None and c['data'].startswith('0xf3cd914c'):
    d=bytes.fromhex(c['data'][10:]);amount=int.from_bytes(d[192:224],'big',signed=True)
    if not 0<args.output<1<<127 or not -(1<<127)<amount<0:raise ValueError('delta bounds')
    delta=(args.output<<128)+(amount%(1<<128));s['getters'].setdefault(c['to'],{})[c['data']]='0x'+delta.to_bytes(32,'big').hex();continue
   if args.settle:
    sel=c['data'][:10]
    if sel in ('0x0b0d9c09','0xa5841194'):value='0x'
    elif sel=='0xa9059cbb':value='0x'+(1).to_bytes(32,'big').hex()
    elif sel=='0x11da60b4':value='0x'+(-amount).to_bytes(32,'big').hex()
    else:break
    s['getters'].setdefault(c['to'],{})[c['data']]=value;mocks.append(dict(call=c,response=value));continue
   break
  rows.append(dict(original_tx=original,tx=tx,command_offset=offset,command_stop=offsets[index+1],synthetic_inputs=mocks,stages=stages,result=r));print(prefix,r['error'],[(c['to'],c['data'][:10]) for c in r['calls']],flush=True)
 Path('reports/amm/router0480-v4-command.json' if args.output is None else 'reports/amm/router0480-v4-output-'+str(args.output)+('-settled' if args.settle else '')+'.json').write_text(json.dumps(dict(synthetic_output=args.output,cases=rows,caveat='Isolated opcode06/a3 command table, synthetic zero inventory and manager callback harness. Actual router code; manager ignores callback failure. No original/full swap execution claim.'),indent=2)+'\n')
if __name__=='__main__':main()
