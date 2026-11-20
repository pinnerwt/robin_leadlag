import copy
import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from packed_routers import decode_packed, ROUTER_29
from v3_calldata import decode

class RouterExtensions(unittest.TestCase):
    def setUp(self):
        self.registry=json.loads((ROOT/'config/optimistic-router-template.json').read_text())
        self.fixtures=json.loads((ROOT/'tests/fixtures/router_extensions.json').read_text())

    def test_archived_bytecode_call_fields(self):
        for f in self.fixtures:
            with self.subTest(router=f['router'],tx=f['tx']):
                op=decode_packed(f['router'],f['calldata'],self.registry)[0]
                self.assertEqual({k:op[k] for k in f['expected']},f['expected'])
                self.assertEqual(decode(f['router'],f['calldata'],{op['pool']:{}},set(),packed_registry=self.registry),[op])

    def test_unrecorded_pool_is_ignored(self):
        for f in self.fixtures:
            self.assertEqual(decode(f['router'],f['calldata'],{},set(),packed_registry=self.registry),[])

    def test_original_packed_unrecorded_pool_is_ignored(self):
        for f in json.loads((ROOT/'tests/fixtures/packed_router_calls.json').read_text()):
            self.assertEqual(decode(f['router'],f['calldata'],{},set(),packed_registry=self.registry),[])

    def test_truncated_calls_and_reference_branch_reject(self):
        for f in self.fixtures:
            with self.assertRaises(ValueError):decode_packed(f['router'],f['calldata'][:40],self.registry)
        f=next(x for x in self.fixtures if x['router'].startswith('0x9e'))
        raw=bytearray.fromhex(f['calldata'][2:]);raw[53]=1
        with self.assertRaisesRegex(ValueError,'reference'):decode_packed(f['router'],raw,self.registry)

    def test_balance_cap_remains_unknown_only_for_tracked_pool(self):
        f=next(x for x in self.fixtures if x['router']==ROUTER_29)
        raw=bytearray.fromhex(f['calldata'][2:]);raw[6]|=4
        with self.assertRaisesRegex(ValueError,'vault'):decode(ROUTER_29,raw,{f['expected']['pool']:{}},set(),packed_registry=self.registry)
        self.assertEqual(decode(ROUTER_29,raw,{},set(),packed_registry=self.registry),[])

    def test_unknown_index_cannot_be_called_unrecorded(self):
        f=next(x for x in self.fixtures if x['router']==ROUTER_29)
        raw=bytearray.fromhex(f['calldata'][2:]);raw[4:6]=b'\xff\xff'
        with self.assertRaisesRegex(ValueError,'unknown packed pool index'):decode(ROUTER_29,raw,{},set(),packed_registry=self.registry)

    def test_29_multi_keeps_only_recorded_pools_in_original_order(self):
        fixtures=json.loads((ROOT/'tests/fixtures/router29_multi.json').read_text())
        for f in fixtures:
            tx=f['tx'];pools={a:{} for a in f['tracked_pools']}
            ops=decode(tx['to'],tx['data'],pools,set(),packed_registry=self.registry)
            self.assertEqual(ops,f['expected'])
            self.assertEqual(decode(tx['to'],tx['data'],{},set(),packed_registry=self.registry),[])
            self.assertTrue(all(op['attempt_policy']=='assume_subcall_success' for op in ops))

    def test_29_unknown_index_in_multi_is_not_silently_ignored(self):
        f=json.loads((ROOT/'tests/fixtures/router29_multi.json').read_text())[0]
        raw=bytearray.fromhex(f['tx']['data'][2:]);raw[4:6]=b'\xff\xff'
        with self.assertRaisesRegex(ValueError,'unknown packed pool index'):
            decode(ROUTER_29,raw,{},set(),packed_registry=self.registry)

    def test_mixed_standard_multicall_keeps_tracked_operation(self):
        w=lambda x:x.to_bytes(32,'big')
        token0,token1,other=1,2,3
        def single(a,b):return bytes.fromhex('04e45aaf')+b''.join(w(x) for x in [a,b,500,0,123,0,0])
        children=[single(token0,other),single(token0,token1)]
        tails=[w(len(c))+c+b'\0'*((-len(c))%32) for c in children]
        payload=w(32)+w(2)+w(64)+w(64+len(tails[0]))+b''.join(tails)
        router='0x'+'aa'*20;pool='0x'+'bb'*20
        pools={pool:dict(tokens=['0x'+format(token0,'040x'),'0x'+format(token1,'040x')],fee=500)}
        ops=decode(router,bytes.fromhex('ac9650d8')+payload,pools,{router})
        self.assertEqual(len(ops),1);self.assertEqual(ops[0]['pool'],pool)

if __name__=='__main__':unittest.main()
