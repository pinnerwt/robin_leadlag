import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_hook_mutability import inspect
class HookMutabilityTest(unittest.TestCase):
 def test_push_data_is_not_opcode(self):
  self.assertTrue(inspect(bytes([0x63,0x55,0xf2,0xf4,0xff,0x00]))['storage_immutable_by_runtime'])
 def test_mutation_mechanisms_detected(self):
  for op in [0x55,0xf2,0xf4,0xff]:self.assertFalse(inspect(bytes([op]))['storage_immutable_by_runtime'])
 def test_sload_location_and_bad_push(self):
  self.assertEqual(inspect(bytes([0x60,0x00,0x54]))['storage_reads'],[2])
  with self.assertRaises(ValueError):inspect(bytes([0x7f,0x00]))
if __name__=='__main__':unittest.main()
