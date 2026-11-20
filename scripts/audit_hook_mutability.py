"""Audit EVM runtime mutation mechanisms, skipping PUSH immediate bytes."""
MUTATORS={0x55:'SSTORE',0xf2:'CALLCODE',0xf4:'DELEGATECALL',0xff:'SELFDESTRUCT'}
def inspect(code):
    code=bytes.fromhex(code.removeprefix('0x')) if isinstance(code,str) else code
    cursor=0;mutators=[];reads=[]
    while cursor<len(code):
        pc=cursor;op=code[cursor];cursor+=1
        if op in MUTATORS:mutators.append(dict(pc=pc,opcode=MUTATORS[op]))
        if op==0x54:reads.append(pc)
        if 0x60<=op<=0x7f:
            cursor+=op-0x5f
            if cursor>len(code):raise ValueError('truncated PUSH')
    return dict(runtime_bytes=len(code),storage_reads=reads,mutation_instructions=mutators,
                storage_immutable_by_runtime=not mutators)

if __name__=='__main__':
    import json
    from pathlib import Path
    from bootstrap_state import hashhex
    hook='0x4adbfa936020fb330587ee1862478316da5ba0cc'
    seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
    code=seed['accounts'][hook]['code'];report=inspect(code)
    assert report['storage_immutable_by_runtime'] and report['storage_reads']==[655]
    report.update(address=hook,code_hash=hashhex(bytes.fromhex(code[2:])),anchor_hash=seed['anchor']['hash'],
                  caveat='Applies to this pinned runtime only; constructor state still requires initialization. Does not infer missing flags as zero.')
    Path('reports/amm/v4-hook-mutability.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
