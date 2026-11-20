"""Freeze a prefix of an active zstd tape without stopping its websocket readers.
The output is explicitly an incomplete prefix, never a clean capture end.
"""
import argparse,json,shutil,struct,subprocess,tempfile
from pathlib import Path
from tape import MAGIC,MAX_FRAME
p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
with tempfile.TemporaryDirectory() as directory:
 frozen=Path(directory)/'prefix.zst';shutil.copyfile(a.source,frozen)
 proc=subprocess.Popen(['zstd','-q','-dc',str(frozen)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 count=0;tail=0
 with a.output.open('wb') as output:
  if proc.stdout.read(8)!=MAGIC:raise ValueError('invalid magic')
  output.write(MAGIC)
  while header:=proc.stdout.read(4):
   if len(header)<4:tail=len(header);break
   n=struct.unpack('<I',header)[0]
   if not 0<n<=MAX_FRAME:raise ValueError('bad frame size')
   frame=proc.stdout.read(n)
   if len(frame)!=n:tail=4+len(frame);break
   output.write(header);output.write(frame);count+=1
 proc.stdout.close();error=proc.stderr.read();status=proc.wait()
 a.output.with_suffix('.prefix.json').write_text(json.dumps(dict(source=str(a.source),source_bytes=frozen.stat().st_size,records=count,discarded_incomplete_tail_bytes=tail,zstd_exit=status,complete_capture=False),indent=2)+'\n')
 print('frozen prefix',count,'records; complete_capture=false')
