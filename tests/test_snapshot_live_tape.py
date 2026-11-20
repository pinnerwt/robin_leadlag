import io,json,struct,subprocess,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from snapshot_live_tape import snapshot
from tape import MAGIC,write_record,records
class SnapshotTest(unittest.TestCase):
 def test_only_complete_frames_and_cutoff(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);raw=io.BytesIO();raw.write(MAGIC)
   write_record(raw,dict(kind='test',recv_ns=1));write_record(raw,dict(kind='test',recv_ns=3))
   raw.write(struct.pack('<I',10)+b'123')
   (root/'source.zst').write_bytes(subprocess.check_output(['zstd','-q','-c'],input=raw.getvalue()))
   info=snapshot(root/'source.zst',root/'copy.zst',2)
   rows=list(records([root/'copy.zst']))
   self.assertEqual(rows[0]['recv_ns'],1);self.assertEqual(rows[-1]['kind'],'snapshot_boundary')
   self.assertEqual(info['skipped_after_cutoff'],1);self.assertTrue(info['dropped_partial_tail'])
if __name__=='__main__':unittest.main()
