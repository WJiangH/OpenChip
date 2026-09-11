"""Independent CN-EXTMEM-01 v0.4 loader and public-channel checker.
Expected behavior derives only from contract sections 2--8 and frozen oracle.
"""
import hashlib
import struct
from collections import Counter
from pathlib import Path
import oracle
BASE=0x20000000
END=0x20100000
RECORD=0x20018100
PROBE=0x20018200
GUARDS=(0x20012ff0,0x20013100,0x20015ff0,0x20016084)
AB=((0x20010000,64),(0x20011000,4096),(0x20014000,5),(0x20015000,165))
CS=((0x20013000,256),(0x20016000,132))
def byte_set(regions):
    return {a+i for a,n in regions for i in range(n)}
INPUT_BYTES=byte_set(AB)
C_BYTES=byte_set(CS)
RECORD_BYTES=byte_set(((RECORD,28),(RECORD+44,4)))
PROBE_BYTES={PROBE+i for i in (1,6,7,12,13,14,15)}
WRITE_BYTES=C_BYTES|set(range(RECORD,RECORD+64))|PROBE_BYTES|set(range(0x20020000,0x20030000))
ADDR_FIELDS={'addr':32,'id':6,'len':8,'size':3,'burst':2,'lock':1,'cache':4,'prot':3,'qos':4,'region':4}
FIELDS={'ar':ADDR_FIELDS,'aw':ADDR_FIELDS,'w':{'data':128,'strb':16,'last':1},'r':{'data':128,'id':6,'resp':2,'last':1},'b':{'id':6,'resp':2}}
def require(ok, message):
    if not ok: raise AssertionError(message)
def load_elf(path):
    """Validate complete ELF before writing an image; CNEM-05/07."""
    raw=Path(path).read_bytes()
    require(len(raw)>=52 and raw[:7]==b'\x7fELF\x01\x01\x01','ELF32 little endian required')
    h=struct.unpack_from('<16sHHIIIIIHHHHHH',raw)
    _,typ,machine,version,entry,phoff,shoff,flags,ehsize,phsize,phnum,shsize,shnum,shstr=h
    require(typ==2 and machine==243 and version==1 and ehsize==52 and phsize==32,'ELF header')
    require(BASE<=entry<BASE+0x10000 and entry%2==0,'entry range/alignment')
    require(phoff+phnum*32<=len(raw),'truncated program headers')
    segments=[]
    for i in range(phnum):
        ptype,off,va,pa,fs,ms,pflags,align=struct.unpack_from('<8I',raw,phoff+32*i)
        if ptype!=1: continue
        require(va==pa and fs<=ms and off+fs<=len(raw),'PT_LOAD shape')
        if not ms: continue
        windows=((BASE,BASE+0x10000),(BASE+0x20000,BASE+0x30000))
        require(any(lo<=va and va+ms<=hi for lo,hi in windows),'PT_LOAD reserved/crossing extent')
        require(not(pflags&1) or va+ms<=BASE+0x10000,'executable outside code')
        require(all(va+ms<=x[0] or x[0]+x[1]<=va for x in segments),'PT_LOAD overlap')
        segments.append((va,ms,off,fs,pflags))
    require(any(a<=entry<a+n and fl&1 for a,n,o,f,fl in segments),'entry not executable')
    mem=bytearray(END-BASE)
    for a,n,o,f,fl in segments: mem[a-BASE:a-BASE+f]=raw[o:o+f]
    return mem,{'entry':entry,'segments':segments,'elf_sha256':hashlib.sha256(raw).hexdigest()}
def initial_image(path,salt,run_id):
    mem,info=load_elf(path)
    for c,(aa,ba) in enumerate(((0x20010000,0x20011000),(0x20014000,0x20015000))):
        a,b=oracle.inputs(c,salt)
        for addr,vals in ((aa,a),(ba,[v for row in b for v in row])):
            mem[addr-BASE:addr-BASE+len(vals)]=bytes(v&255 for v in vals)
    for a,n in (*CS,*[(g,16) for g in GUARDS],(PROBE,32)):
        mem[a-BASE:a-BASE+n]=b'\xa5'*n
    struct.pack_into('<II',mem,0x18000,salt,run_id)
    info['image_sha256']=hashlib.sha256(mem).hexdigest()
    return mem,info

def address_check(p,read):
    require(p['id'] in ((0,1) if read else (0,)),'CNEM-12 ID')
    require(p['size'] in (0,1,2,4) and p['addr']%(1<<p['size'])==0,'CNEM-12 size/alignment')
    require(all(p[k]==v for k,v in {'len':0,'burst':1,'prot':2,'lock':0,'cache':0,'qos':0,'region':0}.items()),'CNEM-12 attributes')
    if p['id']==1: require(p['size']==4,'CNEM-12 fetch size')

def snapshot_read(memory,p):
    data=0
    if not BASE<=p['addr']<END: return 0,3
    for j in range(1<<p['size']):
        data |= memory[p['addr']-BASE+j] << (8*((p['addr']+j)&15))
    return data,0

class Checker:
    def __init__(self,image,config):
        self.mem=bytearray(image); self.initial=bytes(image); self.config=config
        self.reads={}; self.aw=None; self.w=None; self.write=None; self.prev={}
        self.read_bytes=set(); self.fetch_bytes=set(); self.written=set()
        self.probe_reads=set(); self.probe_stores=set(); self.ret_values=[]
        self.counts=Counter(); self.release=None; self.halt=None; self.magic=False
        self.terminal_mem=None
    def process(self,cycle,snapshot,status):
        require(status['fault']==0,'CNEM-11 top fault pulse')
        for ch,s in snapshot.items():
            old=self.prev.get(ch)
            if old and old['valid'] and not old['ready']:
                require(s['valid'] and s['p']==old['p'],f'CNEM-18 {ch} producer changed under stall')
            if s['valid'] and not s['ready']: self.counts['stall_'+ch]+=1
            self.prev[ch]=s
        for channel in ('r','b'):
            if snapshot[channel]['valid']:
                p=snapshot[channel]['p']
                q=self.reads.get(p['id']) if channel=='r' else self.write
                require(q is not None and cycle>q['cycle'],'CNEM-13 unsolicited/early presented '+channel)
                expected=({'id':q['id'],'data':q['expected'],'resp':q['resp'],'last':1}
                          if channel=='r' else {'id':0,'resp':q['resp']})
                require(p==expected,'CNEM-13/15 presented response payload '+channel)
        for channel in ('ar','aw'):
            if snapshot[channel]['valid']: address_check(snapshot[channel]['p'],channel=='ar')
        if snapshot['w']['valid']: require(snapshot['w']['p']['last']==1,'CNEM-12 presented WLAST')
        hs={ch:s['p'] for ch,s in snapshot.items() if s['valid'] and s['ready']}
        # Responses retire old entries before this edge's new requests.
        if 'r' in hs:
            p=hs['r']; require(p['id'] in self.reads,'CNEM-13 unsolicited/wrong-ID R')
            q=self.reads.pop(p['id']); require(cycle>q['cycle'],'CNEM-13 early R')
            require(p=={'id':q['id'],'data':q['expected'],'resp':q['resp'],'last':1},'CNEM-15 R payload mismatch')
            if p['resp']==0:
                covered=set(range(q['addr'],q['addr']+(1<<q['size'])))
                (self.fetch_bytes if p['id'] else self.read_bytes).update(covered)
                if not p['id'] and q['addr'] in (PROBE+1,PROBE+6,PROBE+12):
                    # CNEM-17 readback is a successful read after B-completed store,
                    # not an incidental read of the initialized 0xa5 sentinel.
                    required={PROBE+1:(0,0x5a),PROBE+6:(1,0x1234),PROBE+12:(2,0x89abcdef)}
                    size,value=required[q['addr']]
                    if q['size']==size and covered<=self.written and p['data']==value<<(8*(q['addr']&15)):
                        self.probe_reads.add((q['addr'],q['size']))
            self.counts['r']+=1
        if 'b' in hs:
            require(self.write is not None,'CNEM-13 unsolicited B')
            q=self.write; require(cycle>q['cycle'] and hs['b']=={'id':0,'resp':q['resp']},'CNEM-13 B mismatch/early')
            if q['resp']==0: self.written.update(q['bytes'])
            self.write=None; self.counts['b']+=1
        if 'ar' in hs:
            p=hs['ar']; address_check(p,True)
            require(p['id'] not in self.reads,'CNEM-14 read outstanding bound')
            if p['id']==0: require(self.aw is None and self.w is None and self.write is None,'CNEM-14 data outstanding bound')
            data,resp=snapshot_read(self.mem,p)
            self.reads[p['id']]={**p,'cycle':cycle,'expected':data,'resp':resp}
            self.counts['ar']+=1
        if 'aw' in hs:
            p=hs['aw']; address_check(p,False)
            require(self.aw is None and self.write is None and 0 not in self.reads,'CNEM-14 AW bound')
            self.aw={**p,'cycle':cycle}; self.counts['aw']+=1
        if 'w' in hs:
            require(self.w is None and self.write is None and 0 not in self.reads,'CNEM-14 W bound')
            require(hs['w']['last']==1,'CNEM-12 WLAST')
            self.w={**hs['w'],'cycle':cycle}; self.counts['w']+=1
        if self.aw is not None and self.w is not None:
            a,w=self.aw,self.w; size=1<<a['size']; base=a['addr']&~15
            legal=((1<<size)-1)<<(a['addr']&15)
            require(w['strb']&~legal==0,'CNEM-15 strobe outside transfer')
            changed={base+j for j in range(16) if w['strb']>>j&1}
            resp=0 if BASE<=a['addr']<END else 3
            if resp==0:
                require(changed<=WRITE_BYTES,'CNEM-28 illegal write footprint/code/guard')
                require(self.halt is None,'CNEM-22 late data write')
                require(not(self.magic and changed&C_BYTES),'CNEM-20 result write after magic')
                if changed & set(range(RECORD,RECORD+64)):
                    require(not self.magic,'CNEM-20 record write after magic')
                    if RECORD in changed:
                        require(set(range(RECORD,RECORD+4))<=changed,'partial magic')
                        require(RECORD_BYTES-set(range(RECORD,RECORD+4))<=self.written,'CNEM-20 early magic')
                        require(C_BYTES<=self.written,'CNEM-20 magic before result completion')
                        self.magic=True
                for addr in changed: self.mem[addr-BASE]=(w['data']>>(8*(addr&15)))&255
                ret=self.config['ret']
                if changed & set(range(ret,ret+4)):
                    require(set(range(ret,ret+4))<=changed,'partial return store')
                    self.ret_values.append(struct.unpack_from('<I',self.mem,ret-BASE)[0])
                if a['addr'] in (PROBE+1,PROBE+6,PROBE+12): self.probe_stores.add((a['addr'],a['size']))
            self.write={'cycle':max(a['cycle'],w['cycle']),'bytes':changed,'resp':resp}
            self.aw=self.w=None
        for q in self.reads.values(): require(cycle<q['cycle']+256,'CNEM-19 R deadline')
        if self.write: require(cycle<self.write['cycle']+256,'CNEM-19 B deadline')
        for q in (self.aw,self.w):
            if q: require(cycle<q['cycle']+64,'CNEM-19 unmatched half deadline')
        if self.release is not None:
            if status['halted']:
                require(status['wfi']==0,'CNEM-22 WFI on halt')
                if self.halt is None:
                    self.accept(); self.halt=cycle; self.terminal_mem=bytes(self.mem)
                else: require(bytes(self.mem)==self.terminal_mem,'CNEM-22 memory changed after halt')
            if self.halt is None: require(cycle-self.release<1000000,'CNEM-19 terminal deadline')
            if self.halt is not None:
                require(status=={'halted':1,'fault':0,'wfi':0},'CNEM-22 unstable terminal status')
    def accept(self):
        require(self.aw is None and self.w is None and self.write is None and 0 not in self.reads,'CNEM-22 incomplete data response')
        require(INPUT_BYTES<=self.read_bytes,'CNEM-28 input read coverage')
        require(C_BYTES|RECORD_BYTES|PROBE_BYTES<=self.written,'CNEM-28 write coverage')
        require(set(range(0x20018000,0x20018008))<=self.read_bytes,'descriptor reads')
        for a in (self.config['entry'],self.config['kernel']):
            require(set(range(a,a+4))<=self.fetch_bytes,'CNEM-28 designated fetch bytes')
        sig=[]
        for c,(a,n) in enumerate(CS):
            values=oracle.gemv(*oracle.inputs(c,self.config['salt'])); expected=oracle.int32_bytes(values)
            got=bytes(self.mem[a-BASE:a-BASE+n]); require(got==expected,f'CNEM-22 C{c} expected={expected.hex()} observed={got.hex()}')
            sig.append(oracle.signature(values))
        for a in GUARDS: require(self.mem[a-BASE:a-BASE+16]==b'\xa5'*16,'CNEM-22 guard')
        require(bytes(self.mem[PROBE-BASE:PROBE-BASE+32])==oracle.expected_probe(),'CNEM-22 probe')
        probes={(PROBE+1,0),(PROBE+6,1),(PROBE+12,2)}
        require(probes<=self.probe_reads and probes<=self.probe_stores,'CNEM-17 exact width read/write probes')
        record=[0x434e454d,1,self.config['run_id'],0,*sig,2,0,0,0,0,0,0,0,0,0]
        expected=struct.pack('<16I',*record); got=bytes(self.mem[RECORD-BASE:RECORD-BASE+64])
        require(got==expected,f'CNEM-22 record expected={expected.hex()} observed={got.hex()}')
        require(len(self.ret_values)>=2 and self.ret_values[0]==0x0badd00d and self.ret_values[-1]==0,'CNEM-22 return sentinel/actual')
        require(struct.unpack_from('<I',self.mem,self.config['ret']-BASE)[0]==0,'CNEM-22 final return')
        if self.config['schedule']=='P1':
            require(self.counts['stall_ar'] and (self.counts['stall_aw'] or self.counts['stall_w']),'CNEM-19 P1 NOT_EXERCISED request stalls')
    def summary(self):
        return {'counts':dict(self.counts),'input_bytes':len(INPUT_BYTES&self.read_bytes),'output_bytes':len(C_BYTES&self.written),'record_bytes':len(RECORD_BYTES&self.written),'probe_bytes':len(PROBE_BYTES&self.written),'ret_stores':self.ret_values,'release_cycle':self.release,'halt_cycle':self.halt}
