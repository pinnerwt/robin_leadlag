"""Background fixed-block router dependency verification; never used by reducers."""
import copy
from bootstrap_state import hashhex, mapping


def refresh_registry(template, anchor, rpc, stopped=None, code_hash=hashhex):
    refreshed=copy.deepcopy(template)
    refreshed['anchor']=anchor['number'];refreshed['anchor_hash']=anchor['hash']
    targets=[]
    for address,profile in refreshed['routers'].items():
        targets.append((address,profile))
        for dependency in profile.get('dependencies',[]):
            if dependency.get('dependencies'):raise ValueError('nested dependency inventory must be flattened')
            targets.append((dependency['address'],dependency))
    for address,profile in targets:
        if stopped is not None and stopped.is_set():raise RuntimeError('registry refresh cancelled')
        block=refreshed['anchor']
        code=rpc('eth_getCode',[address,block])
        if code_hash(bytes.fromhex(code[2:]))!=profile['code_hash']:
            raise ValueError('router dependency bytecode changed: '+address)
        if profile.get('implementation_slot'):
            value=int(rpc('eth_getStorageAt',[address,profile['implementation_slot'],block]),16)
            implementation='0x'+(value&((1<<160)-1)).to_bytes(20,'big').hex()
            if implementation!=profile['implementation']:raise ValueError('router implementation changed: '+address)
            code=rpc('eth_getCode',[implementation,block])
            if code_hash(bytes.fromhex(code[2:]))!=profile['implementation_code_hash']:
                raise ValueError('router implementation bytecode changed: '+address)
        for slot,expected in profile.get('required_storage',{}).items():
            value=rpc('eth_getStorageAt',[address,slot,block])
            if int(value,16)!=int(expected,16):raise ValueError('router routing configuration changed: '+address+' '+slot)
        for index in profile.get('pool_indexes',{}):
            value=int(rpc('eth_getStorageAt',[address,mapping(int(index),profile['mapping_slot']),block]),16)
            profile['pool_indexes'][index]='0x'+(value&((1<<160)-1)).to_bytes(20,'big').hex()
            if 'pool_configs' in profile:profile['pool_configs'][index]=hex(value)
    head=rpc('eth_getBlockByNumber',[refreshed['anchor'],False])
    if head['hash']!=refreshed['anchor_hash']:raise ValueError('router snapshot anchor changed')
    return refreshed
