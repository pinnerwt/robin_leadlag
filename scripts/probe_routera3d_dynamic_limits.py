"""Actual single index-6 router limits under reached hook reference states."""
import argparse,copy,json,subprocess,tempfile
from pathlib import Path
from routera3d_v4 import HOOK,MANAGER,WETH,USDG
from routera3d_settings import PARENT
from probe_routera3d_hook_fee import IMPL
from probe_routera3d_hook_sequence import STATE
from validate_routera3d_multiroute import enc
from routera3d_price import PRICE_XOR,route_fields,reverse_v3_limit,forward_v3_limit
from routera3d_hook import directional_fees,DEFAULT_CONFIG
from v3_calldata import word

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('seed');a=ap.parse_args()
    original=json.load(open(a.seed));sequence=json.loads(Path('reports/amm/routera3d-hook-sequence-probe.json').read_text())['cases']
    ref=json.loads(Path('reports/amm/routera3d-v4-sell-probe.json').read_text())['cases'][0]['transaction']
    poolslot='0xa652248898f7392773fb86e84bf1ef4cf17b449600f2d309595c039285782ad8';cases=[]
    with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
        for source in (sequence[0],sequence[1],sequence[8]):
            seed=copy.deepcopy(original);state=int(source['after'],16);block=ref['sequence']
            state=(state&~((1<<40)-1))|block # relocate reference block to avoid expired compressed envelope
            seed['accounts'][HOOK]['storage'][STATE]=hex(state)
            seed['execute_targets'] += [HOOK,MANAGER];seed.setdefault('delegate_targets',[]).append(IMPL)
            key='0x70a08231'+enc(int(PARENT,16))[2:]
            seed['getters'][WETH][key]=enc(10**18);seed['getters'][USDG][key]=enc(10**12)
            sqrt=int(seed['accounts'][MANAGER]['storage'][poolslot],16)&((1<<160)-1)
            fees=directional_fees(state,DEFAULT_CONFIG,sqrt,block)
            requests=[]
            for side,price in ((1,1900000000),(2,1800000000)):
                raw=bytearray.fromhex(ref['data'][2:]);raw[0]=0xe1
                raw[1:6]=int(f'{price ^ PRICE_XOR:040b}'[::-1],2).to_bytes(5,'big');raw[6:9]=((65536<<7)|8).to_bytes(3,'big')
                requests.append(dict(ref,data='0x'+(raw[:13]+bytes.fromhex('69f6')+side.to_bytes(2,'big')).hex(),sequence=block))
            Path(tmp.name).write_text(json.dumps(seed))
            rows=list(map(json.loads,subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=''.join(json.dumps(t)+'\n' for t in requests),text=True).splitlines()))
            for tx,row in zip(requests,rows):
                swaps=[c for c in row['execution_calls'] if c['data'].startswith('0xf3cd914c')]
                if len(swaps)!=1:
                    Path('/tmp/a3d-dynamic-limit-failure.json').write_text(json.dumps(dict(tx=tx,state=hex(state),row=row),indent=2))
                    raise ValueError((len(swaps),row['error'],row['calls'],row['output']))
                raw=bytes.fromhex(swaps[0]['data'][10:]);zero=bool(word(raw,5));fee=fees['sell_fee_ppm' if zero else 'buy_fee_ppm']
                p=route_fields(tx['data']);expected=(forward_v3_limit if zero else reverse_v3_limit)(p['price'],10,fee,10)
                cases.append(dict(calldata=tx['data'],state=hex(state),sqrt=sqrt,block=block,zero=zero,fee=fee,expected_limit=expected,actual_limit=word(raw,7),result=row))
    Path('reports/amm/routera3d-dynamic-limits-probe.json').write_text(json.dumps(dict(cases=cases,caveat='Reached hook fee/carry/direction profiles with reference block relocated to the original transaction block, original pool state and synthetic inventory. Actual router arguments; not complete settlement.'),indent=2)+'\n')
    print([(c['zero'],c['fee'],c['actual_limit']==c['expected_limit']) for c in cases])

if __name__=='__main__':main()
