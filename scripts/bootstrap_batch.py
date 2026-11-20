"""Fixed-block bootstrap using Multicall to fit public RPC retention/rate limits."""
import argparse,json,time
from decimal import Decimal
from pathlib import Path
from bootstrap_state import Bootstrap,word,unpack,signed,mapping,simulate
MULTICALL='0xca11bde05977b3631167028862be2a173976ca11'

def aggregate(calls):
    tuples=[]
    for call in calls:
        data=bytes.fromhex(call['data'][2:])
        tuples.append(word(int(call['to'],16))+word(1)+word(96)+word(len(data))+data+b'\0'*((-len(data))%32))
    offset=32*len(tuples);offsets=[]
    for entry in tuples:offsets.append(word(offset));offset+=len(entry)
    data=bytes.fromhex('82ad56cb')+word(32)+word(len(tuples))+b''.join(offsets)+b''.join(tuples)
    return dict(to=MULTICALL,data='0x'+data.hex(),gas='0x1c9c380')

def split(result):
    data=bytes.fromhex(result[2:]);n=lambda offset:int.from_bytes(data[offset:offset+32],'big')
    start=n(0);count=n(start);base=start+32;rows=[]
    for i in range(count):
        item=base+n(base+32*i);success=n(item)==1;pos=item+n(item+32);length=n(pos)
        if pos+32+length>len(data):raise ValueError('truncated aggregate')
        rows.append((success,'0x'+data[pos+32:pos+32+length].hex()))
    return rows

def merge(state,accounts):
    for address,account in accounts.items():
        dst=state['accounts'].setdefault(address,{})
        for k,v in account.items():
            if k=='storage':
                slots=dst.setdefault(k,{})
                for slot,value in v.items():
                    if slot in slots and slots[slot]!=value:raise ValueError(f'inconsistent fixed-block slot {address} {slot}')
                    slots[slot]=value
            else:
                if k in dst and dst[k]!=v:raise ValueError(f'inconsistent fixed-block account {address} {k}')
                dst[k]=v

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--config',type=Path,default=Path('config/push.json'));p.add_argument('--sizes',default='0.02,0.1')
    p.add_argument('--rpc',default='https://rpc-robinhood.blockmachine.io');a=p.parse_args()
    b=Bootstrap(a.rpc);head=b.rpc('eth_getBlockByNumber',['latest',False]);block=head['number'];print('anchor',block,head['hash'],flush=True)
    state=dict(version=1,anchor=head,created_ns=time.time_ns(),accounts={},pools=[],failed=[],rpc_phase='bootstrap_only',storage_complete=False)
    rows=json.loads(a.config.read_text())['pools'];sizes=a.sizes.split(',')
    def batch(calls):
        request=aggregate(calls);outputs=split(b.rpc('eth_call',[request,block]));merge(state,b.trace(request,block))
        if len(outputs)!=len(calls):raise ValueError('aggregate count')
        return outputs
    imm=batch([dict(to=r['pool'],data='0xbcdb4dad') for r in rows]);storage_calls=[];valid=[]
    for row,(ok,data) in zip(rows,imm):
        try:
            if not ok:raise ValueError('getImmutables reverted')
            w=unpack(data)
            if len(w)!=24:raise ValueError('immutable layout')
            lower,upper=map(signed,w[9:11])
            if not 0<=upper-lower<2048:raise ValueError('bin bounds')
            slots=['0x'+word(i).hex() for i in range(4)]
            for i in range(lower,upper+1):slots.extend([mapping(i,4),mapping(i,5)])
            storage_calls.append(dict(to=row['pool'],data='0xdbd035ff'+word(32).hex()+word(len(slots)).hex()+''.join(s[2:] for s in slots)))
            valid.append(dict(row,immutables=data,slot_keys=slots,quote_checks=[]))
        except Exception as e:state['failed'].append(dict(pool=row['pool'],reason=str(e)))
    for row,(ok,data) in zip(valid,batch(storage_calls)):
        if not ok:raise ValueError('pool storage reverted')
        values=unpack(data)[2:];slots=row.pop('slot_keys')
        if len(values)!=len(slots):raise ValueError('slot count')
        mask=(1<<104)-1
        totals=(sum(v&mask for v in values[4::2]),sum((v>>104)&mask for v in values[4::2]))
        if totals!=(values[1]%(1<<128),values[1]>>128):raise ValueError('bin totals mismatch')
        row['storage']=dict(zip(slots,('0x'+word(v).hex() for v in values)))
        row['provider']='0x'+word(unpack(row['immutables'])[8] or values[3])[-20:].hex()
        merge(state,{row['pool'].lower():{'storage':row['storage']}})
    for row,(ok,data) in zip(valid,batch([dict(to=r['provider'],data='0x171755b1') for r in valid])):
        row['quote_trace']=dict(output=data,error=None if ok else 'provider reverted',from_address=MULTICALL)
    for row in valid:
        if row['quote_trace']['error'] or len(row['quote_trace']['output'])!=194:
            state['pools'].append(row);continue
        prices=unpack(row['quote_trace']['output']);requests=[];checks=[]
        for size in list(dict.fromkeys([*sizes,'1000000'])):
            raw=Decimal(size)*10**row['decimals'][0]
            if raw!=int(raw) or not 0<raw<1<<127:raise ValueError('token amount')
            for sell in [True,False]:
                call=simulate(row['pool'],sell,int(raw) if sell else -int(raw),prices)
                requests.append(call);checks.append(dict(seed_only=size not in sizes,size_tokens=size,side='bid' if sell else 'ask',call=call))
        try:
            for check,(ok,data) in zip(checks,batch(requests)):
                check.update(expected=data,error=None if ok else 'execution reverted');row['quote_checks'].append(check)
            state['pools'].append(row);print('seeded',row['pair'],row['pool'],flush=True)
        except Exception as e:
            state['failed'].append(dict(pool=row['pool'],reason=str(e)));print('failed',row['pool'],str(e),flush=True)
        a.output.with_suffix('.partial.json').write_text(json.dumps(state,separators=(',',':')))
    verified=b.rpc('eth_getBlockByNumber',[block,False])
    if verified['hash']!=head['hash']:raise ValueError('anchor reorg')
    state.update(rpc_calls=b.calls,finished_ns=time.time_ns(),anchor_verified=True)
    a.output.write_text(json.dumps(state,separators=(',',':')))
    print('complete',len(state['pools']),'failed',len(state['failed']),'accounts',len(state['accounts']),'calls',b.calls,flush=True)

if __name__=='__main__':main()
