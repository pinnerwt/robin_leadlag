import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from packed_routers import ROUTER_7DEC,decode_packed
from v3_calldata import decode

class Router7decTests(unittest.TestCase):
    def setUp(self):
        self.registry=json.loads((ROOT/'config/optimistic-router-template.json').read_text())
        self.fixtures=json.loads((ROOT/'tests/fixtures/router7dec.json').read_text())
    def test_real_prefix_arguments(self):
        for f in self.fixtures:
            op=decode_packed(ROUTER_7DEC,f['tx']['data'],self.registry)[0]
            self.assertEqual({k:op[k] for k in f['expected']},f['expected'])
    def test_32_independent_bytecode_memory_placements(self):
        rows=json.loads((ROOT/'tests/fixtures/router7dec_memory_variants.json').read_text())
        self.assertEqual(len(rows),32)
        for f in rows:
            op=decode_packed(ROUTER_7DEC,f['calldata'],self.registry)[0]
            self.assertEqual({k:op[k] for k in f['expected']},f['expected'])
    def test_negative_amount_is_not_int32_sign_extension(self):
        f=next(f for f in self.fixtures if f['case']==[0x31,0])
        raw=bytes.fromhex(f['tx']['data'][2:]);op=decode_packed(ROUTER_7DEC,raw,self.registry)[0]
        self.assertGreaterEqual(int.from_bytes(raw[44:48],'big',signed=True),0)
        self.assertLess(op['amount'],0)
    def test_copy_cannot_change_other_abi_fields(self):
        raw=bytearray.fromhex(self.fixtures[0]['tx']['data'][2:]);raw[43]=0x64
        with self.assertRaisesRegex(ValueError,'overwrite'):decode_packed(ROUTER_7DEC,raw,self.registry)
    def test_unverified_continuation_and_truncation_reject(self):
        raw=bytearray.fromhex(self.fixtures[0]['tx']['data'][2:]);raw[-1]=4
        with self.assertRaisesRegex(ValueError,'continuation'):decode_packed(ROUTER_7DEC,raw,self.registry)
        with self.assertRaises(ValueError):decode_packed(ROUTER_7DEC,raw[:-1],self.registry)
    def test_known_unrecorded_pool_ignored(self):
        for f in self.fixtures:self.assertEqual(decode(ROUTER_7DEC,f['tx']['data'],{},set(),packed_registry=self.registry),[])
if __name__=='__main__':unittest.main()
