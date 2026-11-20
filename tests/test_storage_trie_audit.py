import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_storage_trie import audit,decode
from bootstrap_state import hashhex
from arbos_units import rlp
from attach_storage_trie import attach
from pin_storage_tries import repin
class StorageTrieAudit(unittest.TestCase):
 def test_repin_requires_same_root_and_new_anchor_account_proof(self):
  f=self.fixture();head=dict(f['anchor'],number='0x2',hash='new');proof=copy.deepcopy(f['proof']);proof['storageProof']=[]
  result=repin(f,head,proof);self.assertEqual(result['anchor']['hash'],'new');self.assertTrue(audit(result)['complete'])
  bad=copy.deepcopy(proof);bad['storageHash']='0x'+'ff'*32
  with self.assertRaises(ValueError):repin(f,head,bad)
  bad_head=dict(head,stateRoot='0x'+'ff'*32)
  with self.assertRaises(ValueError):repin(f,bad_head,proof)
 def fixture(self):
  leaves=[rlp([bytes.fromhex('3'+'0'*63),rlp(v)]) for v in (7,8)]
  branch=[b'']*17
  for i,n in enumerate(leaves):branch[i]=bytes.fromhex(hashhex(n)[2:])
  root=rlp(branch);storage_hash=hashhex(root);address='0x'+'11'*20
  av=rlp([0,1,bytes.fromhex(storage_hash[2:]),bytes.fromhex(hashhex(b'')[2:])])
  an=rlp([b'\x20'+bytes.fromhex(hashhex(bytes.fromhex(address[2:]))[2:]),av])
  return dict(anchor={'number':'0x1','hash':'anchor','stateRoot':hashhex(an)},proof=dict(address=address,storageHash=storage_hash,accountProof=['0x'+an.hex()],storageProof=[{'proof':['0x'+n.hex() for n in [root]+leaves]}]))
 def test_full_closure_and_missing_branch(self):
  f=self.fixture();r=audit(f);self.assertTrue(r['complete']);self.assertEqual(set(r['hashed_storage'].values()),{'0x7','0x8'})
  f['proof']['storageProof'][0]['proof'].pop();r=audit(f);self.assertFalse(r['complete']);self.assertEqual(len(r['missing_nodes']),1)
 def test_account_root_and_storage_root_mismatch(self):
  f=self.fixture();f['anchor']['stateRoot']='0x'+'ff'*32
  with self.assertRaises(ValueError):audit(f)
 def test_attachment_requires_complete_matching_snapshot(self):
  f=self.fixture();address=f['proof']['address'];seed={'anchor':f['anchor'],'accounts':{address:{'balance':'0x1','nonce':0,'code':'0x'}}}
  out=attach(seed,f);self.assertEqual(len(out['accounts'][address]['complete_hashed_storage']),2)
  self.assertNotIn('complete_hashed_storage',seed['accounts'][address])
  bad=copy.deepcopy(f);bad['proof']['storageProof'][0]['proof'].pop()
  with self.assertRaises(ValueError):attach(seed,bad)
  bad=copy.deepcopy(seed);bad['accounts'][address]['balance']='0x2'
  with self.assertRaises(ValueError):attach(bad,f)
  f=self.fixture();f['proof']['storageHash']='0x'+'ff'*32
  with self.assertRaises(ValueError):audit(f)
 def test_noncanonical_or_truncated_rlp(self):
  for raw in (b'\x81\x01',b'\xb8\x01\x00',b'\xc2\x80',b'\x80\x80'):
   with self.subTest(raw=raw),self.assertRaises(ValueError):decode(raw)
