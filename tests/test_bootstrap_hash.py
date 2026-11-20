import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bootstrap_state import hashhex
class BootstrapHash(unittest.TestCase):
 def test_keccak_vectors(self):
  self.assertEqual(hashhex(b''),'0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470')
  self.assertEqual(hashhex(b'abc'),'0x4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45')
 def test_code_larger_than_linux_single_argument_limit(self):
  self.assertEqual(hashhex(bytes(100000)),'0xc7b536c6438d5aee3fea9bba0bfb55991e7e0177b2f9c5319da1ba5ab089a98f')
