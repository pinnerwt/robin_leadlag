"""Current router code with saved coherent pool getters: cross-anchor research only."""
import argparse,copy,json
from pathlib import Path
from probe_delegated_kind8 import run

def main():
 ap=argparse.ArgumentParser();ap.add_argument("--v4-shift-bps",type=int,default=0);ap.add_argument("--inventory",type=int);ap.add_argument("--unlock",action="store_true");ap.add_argument("--parameter",type=int);ap.add_argument("--synthetic-fill",action="store_true");ap.add_argument("--fill-output",type=int,default=2000000);ap.add_argument("--v3-execute",action="store_true");ap.add_argument("--v3-transfer",action="store_true");ap.add_argument("--v3-balance",action="store_true");ap.add_argument("--native-delta",type=int);ap.add_argument("--usdg-delta",type=int);ap.add_argument("--take-success",action="store_true");ap.add_argument("--inventory-after",type=int);ap.add_argument("--unwrap-success",action="store_true");ap.add_argument("--settle-success",action="store_true");ap.add_argument("--pay-v3",action="store_true");ap.add_argument("--inventory-final",type=int);ap.add_argument("--observation-cumulative",type=int);ap.add_argument("--reverse-balance",action="store_true");ap.add_argument("--v4-execute",action="store_true");ap.add_argument("--v4-transient",action="store_true");ap.add_argument("--v4-take",action="store_true");ap.add_argument("--weth-deposit",action="store_true");ap.add_argument("--seed-weth-inventory",action="store_true");ap.add_argument("--v4-sync",action="store_true");ap.add_argument("--usdg-manager-balance",action="store_true");ap.add_argument("--usdg-payment",action="store_true");ap.add_argument("--seed-usdg-balance",type=int);ap.add_argument("--actual-settle",action="store_true");ap.add_argument("--actual-inventory",action="store_true");ap.add_argument("--v4-state-shift",action="store_true");ap.add_argument("--weth-payment",action="store_true");ap.add_argument("--usdg-output",action="store_true");ap.add_argument("--v4-curve-shift",action="store_true");args=ap.parse_args()
 if args.v4_curve_shift and (not args.v4_shift_bps or args.v4_state_shift):ap.error("curve shift requires nonzero shift and excludes state shift")
 if args.usdg_output and (not args.usdg_manager_balance or args.v3_transfer):ap.error("actual USDG output requires implementation and no synthetic V3 transfer")
 if args.weth_payment and (not args.weth_deposit or args.reverse_balance):ap.error("actual WETH payment requires deposit implementation and no synthetic V3 balance")
 if args.v4_state_shift and not args.v4_shift_bps:ap.error("state shift requires nonzero price shift")
 if args.actual_inventory and (not args.seed_weth_inventory or args.inventory_after is not None or args.inventory_final is not None):ap.error("actual inventory requires explicit storage and no balance response sequence")
 if args.actual_settle and args.settle_success:ap.error("actual settle conflicts with synthetic settle")
 if args.seed_usdg_balance is not None and (not args.usdg_payment or not 0<=args.seed_usdg_balance<1<<256):ap.error("synthetic USDG storage requires payment and uint256 balance")
 if args.usdg_payment and not args.usdg_manager_balance:ap.error("actual USDG payment requires USDG implementation")
 if args.seed_weth_inventory and (not args.weth_deposit or args.inventory is None):ap.error("synthetic WETH storage requires deposit and explicit inventory")
 if args.weth_deposit and not args.v4_take:ap.error("actual WETH deposit requires actual take")
 if args.v4_take and (not args.v4_transient or args.take_success):ap.error("actual take requires actual transient reads and no synthetic take")
 if args.v4_transient and (not args.v4_execute or args.native_delta is not None or args.usdg_delta is not None):ap.error("actual transient reads require V4 execution and no synthetic deltas")
 if args.v4_execute and args.synthetic_fill:ap.error("actual V4 execution cannot use synthetic fill")
 code=json.loads(Path('reports/amm/router7627-code.json').read_text());root=code['address'];base=json.loads(Path('captures/startup-v9-dependencies.json').read_text());p0='0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca';manager='0x8366a39cc670b4001a1121b8f6a443a643e40951';rows=[]
 selected={}
 for row in json.loads(Path('reports/amm/router7627-prefix.json').read_text())['cases']:selected.setdefault(row['tx']['data'][:10],row['tx'])
 for tx in selected.values():
  if args.parameter is not None:
   raw=bytearray.fromhex(tx["data"][2:]);raw[4:8]=args.parameter.to_bytes(4,"big");tx=dict(tx,data="0x"+raw.hex())
  s=dict(base,accounts={a:copy.deepcopy(v) for a,v in base['accounts'].items() if a in (p0,manager,'0x0bd7d308f8e1639fab988df18a8011f41eacad73','0x5fc5360d0400a0fd4f2af552add042d716f1d168',tx['from'].lower(),'0x'+'00'*20)})
  if args.v4_execute:
   from probe_routera3d_hook_fee import IMPL
   for dependency in ("0x987e330f00b79864a07fe81dfac344d0078abcc0",IMPL,"0x0000000000000000000000000000000000000064"):
    s["accounts"][dependency]=copy.deepcopy(base["accounts"][dependency])
   s["execute_targets"]=["0x987e330f00b79864a07fe81dfac344d0078abcc0"]
   s["delegate_targets"]=[IMPL]
  if args.weth_deposit:
   implementation="0xc6b81b429797e0f555440b70cd99e032d7ae947e"
   s["accounts"][implementation]=copy.deepcopy(base["accounts"][implementation])
   s["delegate_targets"].append(implementation)
  if args.seed_weth_inventory:
   slot="0x95d0bd652bf16a514a6cceccc328a4f34e8f6e1eb7feb07492942361a296b60a"
   storage=s["accounts"]["0x0bd7d308f8e1639fab988df18a8011f41eacad73"]["storage"]
   if slot in storage:raise ValueError("refuse to replace known WETH balance")
   storage[slot]=hex(args.inventory)
  if args.usdg_manager_balance:
   token="0x5fc5360d0400a0fd4f2af552add042d716f1d168"
   slot="0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
   impl="0x"+int(s["accounts"][token]["storage"][slot],16).to_bytes(20,"big").hex()
   s["accounts"][impl]=copy.deepcopy(base["accounts"][impl])
   s.setdefault("delegate_targets",[]).append(impl)
  if args.seed_usdg_balance is not None:
   from bootstrap_state import mapping
   storage=s["accounts"]["0x5fc5360d0400a0fd4f2af552add042d716f1d168"]["storage"]
   for index,value in ((1,args.seed_usdg_balance),(6,0)):
    slot=mapping(int(root,16),index)
    if slot in storage:raise ValueError("refuse to overwrite known USDG storage")
    storage[slot]=hex(value)
  synthetic_observations=[]
  if args.observation_cumulative is not None:
   word=int(s['accounts'][p0]['storage']['0x0'],16);index=(word>>184)&65535;slot=hex(8+index);value=((tx['timestamp']-1)&((1<<32)-1))|((args.observation_cumulative% (1<<56))<<32)|(1<<248)
   if slot in s['accounts'][p0]['storage']:raise ValueError('refuse to replace known observation')
   s['accounts'][p0]['storage'][slot]=hex(value);synthetic_observations.append(dict(slot=slot,value=hex(value)))
   next_slot=hex(8+(index+1)%((word>>200)&65535))
   if next_slot not in s['accounts'][p0]['storage']:s['accounts'][p0]['storage'][next_slot]='0x0';synthetic_observations.append(dict(slot=next_slot,value='0x0',reason='explicit synthetic destination observation'))
  synthetic=[]
  if tx['from'].lower() not in s['accounts']:s['accounts'][tx['from'].lower()]=dict(balance='0x0',code='0x',storage={});synthetic.append(tx['from'].lower())
  s['accounts'][root]=dict(balance='0x0',code=code['code'],storage={});s.update(getters={},trace_execution=True,trace_calldata=True,trace_hashes=True,math_targets=[root],control_targets=[root],execute_calls=[]);stages=[]
  intervention=None
  if args.v4_shift_bps:
   slot='0xa652248898f7392773fb86e84bf1ef4cf17b449600f2d309595c039285782ad8';word=int(s['accounts'][manager]['storage'][slot],16);price=word&((1<<160)-1);shifted=price*(10000+args.v4_shift_bps)//10000
   if not 0<shifted<1<<160:raise ValueError('invalid shifted price')
   value=(word>>160<<160)|shifted
   if args.v4_state_shift or args.v4_curve_shift:
    from v4_pool_state import load as load_v4
    from router7627_price_intervention import shift_no_crossing
    key=dict(currency0='0x'+'00'*20,currency1='0x5fc5360d0400a0fd4f2af552add042d716f1d168',fee=0x800000,tick_spacing=1,hooks='0x987e330f00b79864a07fe81dfac344d0078abcc0')
    state=load_v4(s['accounts'][manager]['storage'],key,effective_lp_fee=40,bitmap_words=range(-788,-784))
    if args.v4_curve_shift:
     shifted_state=state.swap(shifted<state.sqrt,1<<200,shifted)
     if shifted_state['sqrt']!=shifted:raise ValueError('curve shift did not reach target')
     value=(word>>184<<184)|((shifted_state['tick']%(1<<24))<<160)|shifted
     s['accounts'][manager]['storage'][hex(int(slot,16)+3)]=hex(shifted_state['liquidity'])
    else:value=shift_no_crossing(state,shifted,word)
    s['accounts'][manager]['storage'][slot]=hex(value)
   s['getters']={manager:{'0x1e2eaeaf'+slot[2:]:'0x'+value.to_bytes(32,'big').hex()}};intervention=dict(original=hex(word),synthetic=hex(value),note='price-only change; saved tick/bitmap retained, not a coherent historical state')
  if args.v4_state_shift:intervention['note']='Synthetic storage and getter price/tick shift; bitmap proves no initialized tick crossed; hook history and fees not reconstructed.'
  if args.v4_curve_shift:intervention.update(curve=shifted_state,note='Synthetic curve advance updates sqrt/tick/liquidity only; fee growth, token balances and hook history not advanced.')
  for _ in range(80):
   r=run(s,tx);stages.append(r)
   if r['error'] or not r['calls']:break
   changed=False
   for c in r['calls']:
    if args.usdg_output and c['caller'].lower()==p0 and c['to']=='0x5fc5360d0400a0fd4f2af552add042d716f1d168' and c['data'].startswith('0xa9059cbb'):
     key=c['to']+':'+c['data']
     if key not in s['execute_calls']:s['execute_calls'].append(key);changed=True
     continue
    if args.weth_payment and c['to']=='0x0bd7d308f8e1639fab988df18a8011f41eacad73' and (c['data'].startswith('0xa9059cbb') or c['data']=='0x70a08231'+int(p0,16).to_bytes(32,'big').hex()):
     key=c['to']+':'+c['data']
     if key not in s['execute_calls']:s['execute_calls'].append(key);changed=True
     continue
    if args.actual_inventory and c['to']=='0x0bd7d308f8e1639fab988df18a8011f41eacad73' and c['data']=='0x70a08231'+int(root,16).to_bytes(32,'big').hex():
     key=c['to']+':'+c['data']
     if key not in s['execute_calls']:s['execute_calls'].append(key);changed=True
     continue
    if args.actual_settle and c['to']==manager and c['data']=='0x11da60b4':
     key=c['to']+':'+c['data']
     if key not in s['execute_calls']:s['execute_calls'].append(key);changed=True
     continue
    if args.usdg_payment and c['to']=='0x5fc5360d0400a0fd4f2af552add042d716f1d168' and c['data'].startswith('0xa9059cbb'+int(manager,16).to_bytes(32,'big').hex()):
     key=c['to']+':'+c['data']
     if key not in s['execute_calls']:s['execute_calls'].append(key);changed=True
     continue
    if args.usdg_manager_balance and c['to']=='0x5fc5360d0400a0fd4f2af552add042d716f1d168' and c['data']=='0x70a08231'+int(manager,16).to_bytes(32,'big').hex():
     key=c['to']+':'+c['data']
     if key not in s['execute_calls']:s['execute_calls'].append(key);changed=True
     continue
    if args.v4_sync and c['to']==manager and c['data'].startswith('0xa5841194'):
     key=c['to']+':'+c['data']
     if key not in s['execute_calls']:s['execute_calls'].append(key);changed=True
     continue
    if args.weth_deposit and c['to']=='0x0bd7d308f8e1639fab988df18a8011f41eacad73' and c['data']=='0xd0e30db0':
     key=c['to']+':'+c['data']
     if key not in s['execute_calls']:s['execute_calls'].append(key);changed=True
     continue
    if args.v4_take and ((c['to']==manager and c['data'].startswith('0x0b0d9c09')) or (c['to']==root and c['data']=='0x')):
     key=c['to']+':'+c['data']
     if key not in s['execute_calls']:s['execute_calls'].append(key);changed=True
     continue
    if args.v4_transient and c['to']==manager and c['data'].startswith('0xf135baaa'):
     key=c['to']+':'+c['data']
     if key not in s['execute_calls']:s['execute_calls'].append(key);changed=True
     continue
    if args.reverse_balance and c['to']=='0x0bd7d308f8e1639fab988df18a8011f41eacad73' and c['data']=='0x70a08231'+int(p0,16).to_bytes(32,'big').hex():
     s['getters'].setdefault(c['to'],{})[c['data']]='0x'+bytes(32).hex();changed=True;continue
    if args.pay_v3 and c['to']=='0x5fc5360d0400a0fd4f2af552add042d716f1d168' and c['data']=='0xa9059cbb'+int(p0,16).to_bytes(32,'big').hex()+args.fill_output.to_bytes(32,'big').hex():
     s['getters'].setdefault(c['to'],{})[c['data']]='0x'+(1).to_bytes(32,'big').hex();changed=True;continue
    if args.settle_success and c['to']==manager and c['data']=='0x11da60b4':
     s['getters'].setdefault(manager,{})[c['data']]='0x'+int(c['value']).to_bytes(32,'big').hex();changed=True;continue
    if args.unwrap_success and c['to']==manager and c['data']=='0xa5841194'+'00'*32:
     key=c['to']+':'+c['data']
     if key not in s['execute_calls']:s['execute_calls'].append(key);changed=True
     continue
    if args.unwrap_success and c['to']=='0x0bd7d308f8e1639fab988df18a8011f41eacad73' and c['data'].startswith('0x2e1a7d4d'):
     s['getters'].setdefault(c['to'],{})[c['data']]='0x';changed=True;continue
    if args.take_success and c['to']==manager and c['data'].startswith('0x0b0d9c09'):
     s['getters'].setdefault(manager,{})[c['data']]='0x';changed=True;continue
    if args.usdg_delta is not None and c['to']==manager and c['data']=='0xf135baaa3f484ce2460dfc29d5b7bb3c02a8996d56dcc3340cd90f6dac693fa44e4d4060':
     s['getters'].setdefault(manager,{})[c['data']]='0x'+(args.usdg_delta%(1<<256)).to_bytes(32,'big').hex();changed=True;continue
    if args.native_delta is not None and c['to']==manager and c['data']=='0xf135baaafa47c3fbc6da32693cc210992343a11434b43c80b13805a65ec6bb65ee9c8b53':
     s['getters'].setdefault(manager,{})[c['data']]='0x'+(args.native_delta%(1<<256)).to_bytes(32,'big').hex();changed=True;continue
    if args.v3_balance and c['to']=='0x5fc5360d0400a0fd4f2af552add042d716f1d168' and c['data']=='0x70a08231'+int(p0,16).to_bytes(32,'big').hex():
     s['getters'].setdefault(c['to'],{})[c['data']]=['0x'+bytes(32).hex(),'0x'+args.fill_output.to_bytes(32,'big').hex()];changed=True;continue
    if args.v3_transfer and c['caller'].lower()==p0 and c['data'].startswith('0xa9059cbb'):
     s['getters'].setdefault(c['to'],{})[c['data']]='0x'+(1).to_bytes(32,'big').hex();changed=True;continue
    if args.v3_execute and ((c['to']==p0 and c['data'].startswith('0x128acb08')) or (c['to']==root and c['data'].startswith('0xfa461e33'))):
     key=c['to']+':'+c['data']
     if key not in s['execute_calls']:s['execute_calls'].append(key);changed=True
     continue
    if args.v4_execute and c['to']==manager and c['data'].startswith('0xf3cd914c'):
     key=c['to']+':'+c['data']
     if key not in s['execute_calls']:s['execute_calls'].append(key);changed=True
     continue
    if args.synthetic_fill and c['to']==manager and c['data'].startswith('0xf3cd914c'):
     delta=(((-10**15)%(1<<128))<<128)|args.fill_output;s['getters'].setdefault(manager,{})[c['data']]='0x'+delta.to_bytes(32,'big').hex();changed=True;continue
    if args.unlock and ((c['to']==manager and c['data'].startswith('0x48c89491')) or (c['to']==root and c['data'].startswith('0x91dd7346'))):
     key=c['to']+':'+c['data']
     if key not in s['execute_calls']:s['execute_calls'].append(key);changed=True
     continue
    if c['scheme']!='StaticCall':continue
    if args.inventory is not None and c['data']=='0x70a08231'+int(root,16).to_bytes(32,'big').hex():
     value='0x'+args.inventory.to_bytes(32,'big').hex();response=value if args.inventory_after is None else [value,'0x'+args.inventory_after.to_bytes(32,'big').hex()]
     if args.inventory_final is not None:
      if not isinstance(response,list):raise ValueError('final balance requires after balance')
      response=response+['0x'+args.inventory_final.to_bytes(32,'big').hex()]
     if s['getters'].get(c['to'],{}).get(c['data'])!=response:s['getters'].setdefault(c['to'],{})[c['data']]=response;changed=True
     continue
    if (c['to']==p0 and c['data'][:10] in ('0x3850c7bd','0x1a686502','0xddca3f43','0x5339c296','0xf30dba93')) or (c['to']==manager and c['data'].startswith('0x1e2eaeaf')):
     key=c['to']+':'+c['data']
     if key not in s['execute_calls']:s['execute_calls'].append(key);changed=True
   if not changed:break
  rows.append(dict(synthetic_v4_curve_shift=args.v4_curve_shift,actual_usdg_output=args.usdg_output,actual_weth_payment=args.weth_payment,synthetic_v4_state_shift=args.v4_state_shift,actual_inventory=args.actual_inventory,actual_settle=args.actual_settle,synthetic_usdg_storage_balance=args.seed_usdg_balance,synthetic_usdg_transfer_flag=0 if args.seed_usdg_balance is not None else None,actual_usdg_payment=args.usdg_payment,actual_usdg_manager_balance=args.usdg_manager_balance,actual_v4_sync=args.v4_sync,synthetic_weth_storage_inventory=args.inventory if args.seed_weth_inventory else None,actual_weth_deposit=args.weth_deposit,actual_v4_take=args.v4_take,actual_v4_transient=args.v4_transient,actual_v4_execution=args.v4_execute,synthetic_reverse_balance=args.reverse_balance,synthetic_observations=synthetic_observations,synthetic_inventory_final=args.inventory_final,synthetic_v3_payment=args.pay_v3,synthetic_settle_success=args.settle_success,synthetic_unwrap_success=args.unwrap_success,synthetic_inventory_after=args.inventory_after,synthetic_take_success=args.take_success,synthetic_usdg_delta=args.usdg_delta,synthetic_native_delta=args.native_delta,synthetic_v3_balance=args.v3_balance,synthetic_v3_transfer=args.v3_transfer,synthetic_fill=({"native_input":10**15,"usdg_output":args.fill_output} if args.synthetic_fill else None),probe_stage_count=len(stages),probe_stage_limit=80,synthetic_inventory=args.inventory,price_intervention=intervention,tx=tx,synthetic_caller_metadata=synthetic,stages=stages,result=r));print(tx['data'],r['error'],r['calls'])
 Path('reports/amm/router7627-local-getters'+('' if not args.v4_shift_bps else '-shift-'+str(args.v4_shift_bps))+('' if args.inventory is None else '-inventory-'+str(args.inventory))+('-unlock' if args.unlock else '')+('' if args.parameter is None else '-parameter-'+str(args.parameter))+('-synthetic-fill' if args.synthetic_fill else '')+('' if args.fill_output==2000000 else '-output-'+str(args.fill_output))+('-v3' if args.v3_execute else '')+('-transfer' if args.v3_transfer else '')+('-balance' if args.v3_balance else '')+('' if args.native_delta is None else '-native-'+str(args.native_delta))+('' if args.usdg_delta is None else '-usdg-'+str(args.usdg_delta))+('-take' if args.take_success else '')+('' if args.inventory_after is None else '-after-'+str(args.inventory_after))+('-unwrap' if args.unwrap_success else '')+('-settle' if args.settle_success else '')+('-paid' if args.pay_v3 else '')+('' if args.inventory_final is None else '-final-'+str(args.inventory_final))+('' if args.observation_cumulative is None else '-obs-'+str(args.observation_cumulative))+('-reverse-balance' if args.reverse_balance else '')+('-v4' if args.v4_execute else '')+('-transient' if args.v4_transient else '')+('-actual-take' if args.v4_take else '')+('-deposit' if args.weth_deposit else '')+('-seed-inventory' if args.seed_weth_inventory else '')+('-sync' if args.v4_sync else '')+('-usdg-balance' if args.usdg_manager_balance else '')+('-usdg-pay' if args.usdg_payment else '')+('' if args.seed_usdg_balance is None else '-usd-'+str(args.seed_usdg_balance))+('-settled' if args.actual_settle else '')+('-actual-inv' if args.actual_inventory else '')+('-state-shift' if args.v4_state_shift else '')+('-weth-pay' if args.weth_payment else '')+('-out' if args.usdg_output else '')+('-curve-shift' if args.v4_curve_shift else '')+'.json').write_text(json.dumps(dict(code_anchor=code['anchor']['number'],state_anchor=base['anchor'],cases=rows,caveat='Explicit current-code/old-state research composition; no historical or same-anchor transaction success. Saved pool getter bytecode/state executed, missing slots stay errors.'),indent=2)+'\n')
if __name__=='__main__':main()
