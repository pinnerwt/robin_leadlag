"""Verify proof links and report complete storage-trie coverage. Offline only.
Missing nodes remain explicit; never infer zero from an incomplete proof set.
"""
import argparse,json,subprocess
from pathlib import Path
from bootstrap_state import hashhex

def decode(raw):
 def item(pos):
  if pos>=len(raw):raise ValueError('truncated RLP')
  first=raw[pos];pos+=1
  if first<128:return bytes([first]),pos
  if first<=183:n=first-128;is_list=False
  elif first<=191:
   z=first-183
   if pos+z>len(raw) or raw[pos]==0:raise ValueError('invalid RLP length')
   n=int.from_bytes(raw[pos:pos+z],'big');pos+=z;is_list=False
   if n<56:raise ValueError('noncanonical RLP length')
  elif first<=247:n=first-192;is_list=True
  else:
   z=first-247
   if pos+z>len(raw) or raw[pos]==0:raise ValueError('invalid list length')
   n=int.from_bytes(raw[pos:pos+z],'big');pos+=z;is_list=True
   if n<56:raise ValueError('noncanonical list length')
  end=pos+n
  if end>len(raw):raise ValueError('truncated RLP payload')
  if not is_list:
   if n==1 and raw[pos]<128:raise ValueError('noncanonical RLP string')
   return raw[pos:end],end
  out=[]
  while pos<end:
   v,pos=item(pos);out.append(v)
  if pos!=end:raise ValueError('RLP list overrun')
  return out,end
 value,end=item(0)
 if end!=len(raw):raise ValueError('trailing RLP')
 return value

def walk(root,nodes):
 leaves={};missing=[];visited=set()
 def node(ref,path,depth=0):
  if depth>65:raise ValueError('trie depth exceeds secure key')
  if isinstance(ref,list):v=ref
  else:
   if ref==b'':return
   if len(ref)!=32:raise ValueError('invalid trie hash reference')
   key=ref.hex();raw=nodes.get(key)
   if raw is None:missing.append(dict(hash='0x'+key,prefix=path));return
   visited.add(key);v=decode(raw)
  if not isinstance(v,list):raise ValueError('invalid trie node')
  if len(v)==17:
   if v[16]:
    if len(path)!=64:raise ValueError('invalid branch key length')
    leaves[path]=v[16]
   for i,child in enumerate(v[:16]):
    if child:node(child,path+format(i,'x'),depth+1)
  elif len(v)==2:
   compact=v[0]
   if not isinstance(compact,bytes) or not compact:raise ValueError('invalid compact path')
   digits=compact.hex();flag=int(digits[0],16)
   if flag>3 or (not flag&1 and digits[1]!='0'):raise ValueError('invalid compact flags')
   suffix=digits[1:] if flag&1 else digits[2:];key=path+suffix
   if len(key)>64:raise ValueError('trie key too long')
   if flag&2:
    if len(key)!=64 or not isinstance(v[1],bytes):raise ValueError('invalid leaf')
    leaves[key]=v[1]
   else:
    if not suffix:raise ValueError('empty extension')
    node(v[1],key,depth+1)
  else:raise ValueError('invalid trie arity')
 if root==hashhex(b'\x80'):return {},[],set()
 node(bytes.fromhex(root[2:]),'');return leaves,missing,visited

def node_map(encoded):
 encoded=list(encoded)
 hashes=json.loads(subprocess.check_output(['target/release/examples/keccak_batch'],input=json.dumps(encoded).encode()))
 if len(hashes)!=len(encoded):raise ValueError('hash count mismatch')
 return {h:bytes.fromhex(n[2:]) for h,n in zip(hashes,encoded)}

def audit(document):
 p=document['proof'];head=document['anchor'];account_nodes=node_map(p['accountProof'])
 accounts,_,_=walk(head['stateRoot'],account_nodes);address_key=hashhex(bytes.fromhex(p['address'][2:]))[2:]
 if address_key not in accounts:raise ValueError('account inclusion not proved against anchor stateRoot')
 account=decode(accounts[address_key])
 if not isinstance(account,list) or len(account)!=4 or account[2].hex()!=p['storageHash'][2:]:raise ValueError('storage root differs from proven account')
 nodes=node_map({n for s in p['storageProof'] for n in s['proof']})
 leaves,missing,visited=walk(p['storageHash'],nodes)
 values={}
 for k,v in leaves.items():
  val=decode(v)
  if not isinstance(val,bytes) or len(val)>32 or (val and val[0]==0):raise ValueError('invalid storage integer')
  values['0x'+k]=hex(int.from_bytes(val,'big'))
 return dict(anchor=head['number'],anchor_hash=head['hash'],account=p['address'],storage_root=p['storageHash'],account_root_verified=True,
  complete=not missing,hashed_storage=values,missing_nodes=missing,reachable_nodes=len(visited),provided_nodes=len(nodes),
  proven_account=dict(nonce=hex(int.from_bytes(account[0],'big')),balance=hex(int.from_bytes(account[1],'big')),code_hash='0x'+account[3].hex()))
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('proof',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 r=audit(json.loads(a.proof.read_text()));a.output.write_text(json.dumps(r,indent=2)+'\n');print('root verified',r['account_root_verified'],'leaves',len(r['hashed_storage']),'missing',len(r['missing_nodes']),'complete',r['complete'])
