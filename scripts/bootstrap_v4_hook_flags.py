"""Explicit initialization-only fixed-block hook flags and runtime verification."""
import json
from pathlib import Path
from bootstrap_state import Bootstrap,mapping,hashhex
from audit_hook_mutability import inspect
from v3_calldata import word,blob,array
from universal_v4_intent import inspect as intent
HOOK='0x4adbfa936020fb330587ee1862478316da5ba0cc'
ROUTER='0x204faca1764b154221e35c0d20abb3c525710498'
def main():
    senders=set()
    for row in map(json.loads,Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines()):
        tx=row['tx']
        if (tx['to'] or '').lower()!=ROUTER:continue
        data=bytes.fromhex(tx['data'][10:])
        for command,payload in zip(blob(data,word(data,0)),array(data,word(data,1))):
            if command!=16:continue
            try:op=intent(payload)
            except ValueError:continue
            if op['hooks']==HOOK:senders.add(tx['from'].lower())
    rpc=Bootstrap('https://rpc-robinhood.blockmachine.io')
    anchor=rpc.rpc('eth_getBlockByNumber',['latest',False]);block=anchor['number']
    code=rpc.rpc('eth_getCode',[HOOK,block]);audit=inspect(code)
    reference=json.loads(Path('reports/amm/v4-hook-mutability.json').read_text())
    digest=hashhex(bytes.fromhex(code[2:]))
    if digest!=reference['code_hash'] or not audit['storage_immutable_by_runtime']:raise ValueError('hook runtime changed')
    entries=[]
    for sender in sorted(senders):
        slot=mapping(int(sender,16),0);value=rpc.rpc('eth_getStorageAt',[HOOK,slot,block])
        entries.append(dict(sender=sender,slot=slot,value=value,flag=bool(int(value,16)&255)))
    check=rpc.rpc('eth_getBlockByNumber',[block,False])
    if check['hash']!=anchor['hash']:raise ValueError('initialization anchor changed')
    report=dict(anchor=anchor,hook=HOOK,code_hash=digest,entries=entries,rpc_calls=rpc.calls,
                scope='Current fixed-block initialization for observed senders only; not inserted into historical seed')
    Path('reports/amm/v4-hook-current-flags.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(block=block,senders=len(entries),flags=[e['flag'] for e in entries])))
if __name__=='__main__':main()
