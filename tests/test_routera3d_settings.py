import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from routera3d_settings import update,transaction_update,parent_postlude,executor_update,PARENT,CHILD

class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.cases=json.loads(Path('tests/fixtures/routera3d_settings.json').read_text())
    def test_bytecode_writes_and_nonmutation(self):
        self.assertEqual(len(self.cases),16)
        for case in self.cases:
            before=copy.deepcopy(case['initial_storage'])
            self.assertEqual(update(case['calldata'],case['initial_storage']),case['expected'])
            self.assertEqual(case['initial_storage'],before)
    def test_missing_or_unknown_never_infers_zero(self):
        with self.assertRaisesRegex(ValueError,'missing initial'):
            update(self.cases[0]['calldata'],{})
        for calldata in ['0x12345678',self.cases[0]['calldata']+'00',self.cases[0]['calldata'][:-2]]:
            with self.assertRaises(ValueError):update(calldata,self.cases[0]['initial_storage'])
    def test_reduction_and_abi_width_checks(self):
        c=self.cases[0]
        raw=bytearray.fromhex(c['calldata'][2:])
        raw[4:36]=(1<<88).to_bytes(32,'big')
        with self.assertRaisesRegex(ValueError,'ABI width'):
            update('0x'+raw.hex(),c['initial_storage'])
        raw[4:36]=((1<<88)-1).to_bytes(32,'big')
        with self.assertRaisesRegex(ValueError,'only reduce'):
            update('0x'+raw.hex(),c['initial_storage'])
    def test_sequential_setters_use_updated_word(self):
        first=self.cases[0]; storage=copy.deepcopy(first['initial_storage'])
        change=update(first['calldata'],storage);storage[change['slot']]=change['after']
        zero=self.cases[1];change=update(zero['calldata'],storage);storage[change['slot']]=change['after']
        with self.assertRaisesRegex(ValueError,'only reduce'):
            update(first['calldata'],storage)

class SettingsWrapperTest(unittest.TestCase):
    def setUp(self):
        self.cases=json.loads(Path('tests/fixtures/routera3d_settings_wrapper.json').read_text())
        self.storage=json.loads(Path('tests/fixtures/routera3d_settings.json').read_text())[0]['initial_storage']
    def test_both_contract_writes_match_bytecode(self):
        self.assertEqual(len(self.cases),24)
        for case in self.cases:
            self.assertEqual(transaction_update(PARENT,case['calldata'],self.storage,case['parent_state']),case['expected'])
    def test_missing_postlude_and_unverified_wrappers_reject(self):
        case=self.cases[0]
        with self.assertRaisesRegex(ValueError,'balance state required'):
            transaction_update(PARENT,case['calldata'],self.storage)
        for offset,value in [(4,123),(36,1),(68,64)]:
            raw=bytearray.fromhex(case['calldata'][2:]);raw[offset:offset+32]=value.to_bytes(32,'big')
            with self.assertRaises(ValueError):transaction_update(PARENT,'0x'+raw.hex(),self.storage,case['parent_state'])
        with self.assertRaises(ValueError):
            transaction_update(PARENT,case['calldata']+'00',self.storage,case['parent_state'])
    def test_tier_preserves_other_bits_and_short_circuit_priority(self):
        old=(1<<256)-1
        for a,b,tier in [(0,0,0),(0,123,1),(123,123,2)]:
            result=parent_postlude(old,a,b)
            self.assertEqual(result['tier'],tier)
            self.assertEqual(result['after']&~(255<<168),old&~(255<<168))
            self.assertFalse(parent_postlude(result['after'],a,b)['write_required'])

class ExecutorTest(unittest.TestCase):
    def test_bytecode_replacement_fixtures(self):
        cases=json.loads(Path('tests/fixtures/routera3d_executor.json').read_text())
        self.assertEqual(len(cases),9)
        for c in cases:
            self.assertEqual(executor_update(c['calldata'],c['slot0'],c['code_hash']),c['expected'])

    def test_unpinned_code_requires_initialization(self):
        c=json.loads(Path('tests/fixtures/routera3d_executor.json').read_text())[0]
        for code_hash in (None,'0x'+'00'*32):
            self.assertTrue(executor_update(c['calldata'],c['slot0'],code_hash)['requires_reinitialization'])

    def test_rejects_malformed_and_self_target(self):
        c=json.loads(Path('tests/fixtures/routera3d_executor.json').read_text())[0]
        for data in (c['calldata']+'00',c['calldata'][:-2],'0x12345678',
                     '0x63f8683b'+int(PARENT,16).to_bytes(32,'big').hex()+'00'*32,
                     '0x63f8683b'+(1<<160).to_bytes(32,'big').hex()+'00'*32):
            with self.assertRaises(ValueError):executor_update(data,c['slot0'])

if __name__=='__main__':unittest.main()
