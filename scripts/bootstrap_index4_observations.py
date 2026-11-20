"""Initialization-only observation snapshot; never merge across anchors."""
import argparse,json
from pathlib import Path
from bootstrap_state import Bootstrap,unpack
from bootstrap_storage import read_slots
POOL='0x7615926023bb149f36095645c2a81dc367d39750'

def snapshot(rpc,block='latest'):
    head=rpc('eth_getBlockByNumber',[block,False])
    if not head or not head.get('hash'):raise ValueError('missing anchor')
    block=head['number']
    result=rpc('eth_call',[{'to':POOL,'data':'0x3850c7bd'},block])
    fields=unpack(result)
    if len(fields)!=6:raise ValueError('unexpected index4 slot0 layout')
    index,cardinality,next_cardinality=fields[2:5]
    if not 0<=index<cardinality<=next_cardinality<=65535:raise ValueError('invalid ring bounds')
    # Initialization allocation may grow up to cardinalityNext. Explicitly read
    # all slots, including zero values: no unknown slot is inferred to be zero.
    slots=read_slots(rpc,block,{POOL:list(range(17,17+next_cardinality))})[POOL]
    current=int(slots[hex(17+index)],16)
    if current>>248!=1:raise ValueError('active observation not initialized')
    # Check raw layout against the contract's own public getter at the same block.
    value=rpc('eth_call',[{'to':POOL,'data':'0x252c09d7'+index.to_bytes(32,'big').hex()},block])
    fields_current=unpack(value)
    tick=(current>>32)&((1<<56)-1)
    if tick&(1<<55):tick-=1<<56
    expected=[current&((1<<32)-1),tick%(1<<256),(current>>88)&((1<<160)-1),current>>248]
    if fields_current!=expected:raise ValueError('observation layout mismatch')
    verify=rpc('eth_getBlockByNumber',[block,False])
    if verify['hash']!=head['hash']:raise ValueError('anchor changed')
    return dict(kind='index4_observation_checkpoint',anchor=head,pool=POOL,slot0=result,
                observation_index=index,cardinality=cardinality,cardinality_next=next_cardinality,
                accounts={POOL:{'storage':slots}},observation_state_complete=True,
                execution_state_complete=False,
                caveat='Only observation ring. Other pool/config/inventory state must share this anchor; never merge into older checkpoints.')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rpc',default='https://rpc.mainnet.chain.robinhood.com')
    ap.add_argument('--block',default='latest');ap.add_argument('--output',required=True)
    a=ap.parse_args();b=Bootstrap(a.rpc,interval=.5)
    result=snapshot(b.rpc,a.block)
    Path(a.output).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(block=result['anchor']['number'],index=result['observation_index'],cardinality=result['cardinality'],slots=len(result['accounts'][POOL]['storage']),rpc_calls=b.calls)))
if __name__=='__main__':main()
