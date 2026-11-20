"""Offline index-6 dependency probe; synthetic first V3 fill, archived V4 getter."""
import argparse,json,subprocess,tempfile
from pathlib import Path
from validate_routera3d_multiroute import P0,CHILD,PARENT,USDG,WETH,enc,runtime,PRICE_XOR

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('seed');ap.add_argument('--cap-exponent',type=int,default=20);ap.add_argument('--settlement-probe',action='store_true');a=ap.parse_args()
    seed=json.load(open(a.seed));ref=json.load(open('tests/fixtures/routera3d_price.json'))[0]
    tx=next(r['tx'] for r in map(json.loads,open('reports/amm/optimistic-target-corpus.jsonl')) if r['tx']['tx']==ref['tx'])
    raw=bytearray.fromhex(tx['data'][2:]);raw[0]=0xe2
    raw[1:6]=int(f'{1900000000 ^ PRICE_XOR:040b}'[::-1],2).to_bytes(5,'big')
    raw[6:9]=((65536<<7)|a.cap_exponent).to_bytes(3,'big')
    tx=dict(tx,data='0x'+(raw[:13]+bytes.fromhex('09f669f60005')).hex())
    seed['control_targets']=[CHILD]
    seed.setdefault('delegate_targets',[]).append('0x3328004ae3b4ee272f25f3a2873f47c2fb678000')
    spent=min(10**9,(65536<<a.cap_exponent)//2);output=spent*600000000;inventory=10**12
    key='0x70a08231'+enc(int(PARENT,16))[2:]
    seed['accounts'][P0]['code']=runtime(CHILD,seed['getters'][P0]['0x3850c7bd'],-output,spent)
    seed['execute_targets'].extend([P0,'0x987e330f00b79864a07fe81dfac344d0078abcc0'])
    seed['getters'][USDG][key]=[enc(inventory)]*3+[enc(inventory-spent)]*16
    seed['getters'][WETH][key]=[enc(0)]*2+[enc(output)]*16
    seed['getters'][USDG]['0xa9059cbb'+enc(int(P0,16))[2:]+enc(spent)[2:]]=enc(1)
    manager='0x8366a39cc670b4001a1121b8f6a443a643e40951'
    seed['execute_targets'].append(manager)
    slot='0xa652248898f7392773fb86e84bf1ef4cf17b449600f2d309595c039285782ad8'
    value=seed['accounts'][manager]['storage'][slot]
    seed['getters'].setdefault(manager,{})['0x1e2eaeaf'+slot[2:]]=enc(int(value,16))
    synthetic_storage=[]
    if a.settlement_probe:
        child_weth_slot='0x22589250d9a8b9671adb5519e61b93e4ba6ca4f94d16b92f628cc7c8461743fd'
        synthetic_storage.append(dict(address=WETH,slot=child_weth_slot,value='0x0',reason='controlled initial child WETH balance, not historical evidence'))
        seed['accounts'][WETH]['storage'][child_weth_slot]='0x0'
        seed.setdefault('execute_calls',[]).append(WETH+':0xd0e30db0')
        seed['delegate_targets'].append('0xc6b81b429797e0f555440b70cd99e032d7ae947e')
    with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
        Path(tmp.name).write_text(json.dumps(seed))
        row=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx)+'\n',text=True))
        synthetic_transfers=[]
        if a.settlement_probe:
            seed['getters'][USDG]['0x70a08231'+enc(int(manager,16))[2:]]=[enc(0),enc(65536<<a.cap_exponent)]
            for _ in range(4):
                calls=row['calls']
                if len(calls)!=1:break
                call=calls[0];data=bytes.fromhex(call['data'][2:])
                if call['to'] not in (WETH,USDG) or len(data)!=68 or data[:4].hex()!='a9059cbb':break
                recipient=int.from_bytes(data[4:36],'big')
                if recipient!=int(PARENT if call['to']==WETH else manager,16):break
                synthetic_transfers.append(call)
                seed['getters'][call['to']][call['data']]=enc(1)
                Path(tmp.name).write_text(json.dumps(seed))
                row=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx)+'\n',text=True))

            swaps=[x for x in row['execution_returns'] if x['selector']=='0xf3cd914c' and x['result']=='Return']
            if len(swaps)==1 and len(synthetic_transfers)==2:
                native=int(swaps[0]['output'],16)>>128
                seed['getters'][USDG][key]=[enc(inventory)]*3+[enc(inventory-spent)]*4+[enc(inventory-spent-(65536<<a.cap_exponent))]*16
                seed['getters'][WETH][key]=[enc(0)]*2+[enc(output)]*2+[enc(output+native)]*16
                Path(tmp.name).write_text(json.dumps(seed))
                row=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx)+'\n',text=True))
    out=dict(synthetic_storage=synthetic_storage,synthetic_transfers=synthetic_transfers,real_deposit=a.settlement_probe,transaction=tx,manager=manager,slot=slot,archived_word=value,result=row,
             caveat='Synthetic V3 fill/inventory and mixed-era router configuration; archived manager word. No historical transaction parity.')
    Path(f'reports/amm/routera3d-index6-probe-{a.cap_exponent}{'-settlement' if a.settlement_probe else ''}.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(dict(error=row['error'],calls=row['calls']),indent=2))

if __name__=='__main__':main()
