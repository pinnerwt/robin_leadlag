"""Decode messages after a checkpoint; older messages are already in its state."""
import argparse,json,subprocess,sys
from pathlib import Path
from tape import records
p=argparse.ArgumentParser(description=__doc__);p.add_argument('checkpoint',type=Path);p.add_argument('tape',nargs='+');a=p.parse_args();n=int(json.loads(a.checkpoint.read_text())['anchor']['number'],16)
proc=subprocess.Popen(['target/release/examples/decode_feed','--with-raw'],stdin=subprocess.PIPE,stdout=sys.stdout,text=True)
try:
 for row in records(a.tape):
  if row.get('kind')!='nitro_push':continue
  messages=row['payload'].get('messages')
  if isinstance(messages,list):
   row['payload']['messages']=[m for m in messages if m['sequenceNumber']>n]
   if not row['payload']['messages']:continue
  proc.stdin.write(json.dumps(row)+'\n')
except BrokenPipeError:pass
finally:
 try:proc.stdin.close()
 except BrokenPipeError:pass
 status=proc.wait()
raise SystemExit(status)
