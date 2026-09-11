"""Independent CNEM-21/23/24/25 negative checker; accepted v0.4 CNEM-31 obligations.
Protocol/lane/deadline mechanics retain the independently reviewed positive
checker. Expected traps derive from contract, never SW/RTL implementation.
"""
from checker import *
NEGATIVE_RECORD_BYTES=byte_set(((RECORD,16),(RECORD+28,20)))

class TrapChecker:
    def __init__(self,image,config):
        self.mem=bytearray(image); self.initial=bytes(image); self.config=config
        self.reads={}; self.aw=None; self.w=None; self.write=None; self.prev={}
        self.read_bytes=set(); self.fetch_bytes=set(); self.written=set()
        self.probe_reads=set(); self.probe_stores=set(); self.ret_values=[]
        self.counts=Counter(); self.release=None; self.halt=None; self.magic=False
        self.terminal_mem=None; self.substitutions=0; self.target_operations=0; self.error_handshakes=[]; self.post_halt_observations=[]
        self.ret_completed=[]; self.pending_terminal_reason=None; self.terminal_commits=None
        self.responder_observation_cycles=[]; self.ret_write_events=[]
        self.sentinel_bytes=set(); self.sentinel_b=None; self.return_bytes=set(); self.first_return_half=None
    def process(self,cycle,snapshot,status):
        if self.halt is not None:
            require(cycle==self.halt+len(self.post_halt_observations)+1,'CNEM-31 consecutive observation edges')
            require(cycle<=self.halt+32,'CNEM-31 exactly 32 observation edges')
            require(status=={'halted':1,'fault':0,'wfi':0},'CNEM-31 unstable terminal status')
            require(bytes(self.mem)==self.terminal_mem,'CNEM-31 aperture changed after terminal')
            require(not any(snapshot[ch]['valid'] and snapshot[ch]['ready'] for ch in ('aw','w')),'CNEM-31 post-terminal write handshake')
            self.post_halt_observations.append({'cycle':cycle,'status':dict(status)})
        require(status['fault']==0,'CNEM-24 negative top fault')
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
            if p['resp']: self.error_handshakes.append({'channel':'r','addr':q['addr'],'id':q['id'],'resp':p['resp'],'cycle':cycle})
            self.counts['r']+=1
        if 'b' in hs:
            require(self.write is not None,'CNEM-13 unsolicited B')
            q=self.write; require(cycle>q['cycle'] and hs['b']=={'id':0,'resp':q['resp']},'CNEM-13 B mismatch/early')
            if q['resp']==0:
                self.written.update(q['bytes'])
                if q['ret_bytes']:
                    event={'bytes':q['ret_bytes'],'first_half':q['first_half'],'b_cycle':cycle}
                    self.ret_write_events.append(event)
                    sentinel=(0x0badd00d).to_bytes(4,'little');returned=(1).to_bytes(4,'little')
                    for offset,value in q['ret_bytes'].items():
                        if value==sentinel[offset]:
                            require(self.first_return_half is None,'CNEM-31 sentinel store after handler return started')
                            self.sentinel_bytes.add(offset)
                        else:self.sentinel_bytes.discard(offset)
                        if value==returned[offset]:
                            require(self.sentinel_b is not None and q['first_half']>self.sentinel_b,'CNEM-31 return byte before sentinel B')
                        if self.sentinel_b is not None:
                            if value==returned[offset]:
                                self.return_bytes.add(offset)
                                self.first_return_half=q['first_half'] if self.first_return_half is None else min(self.first_return_half,q['first_half'])
                            else:self.return_bytes.discard(offset)
                    if self.sentinel_bytes==set(range(4)):self.sentinel_b=cycle
                    if q.get('ret_value') is not None:
                        self.ret_completed.append({'value':q['ret_value'],'first_half':q['first_half'],'b_cycle':cycle})
            else: self.error_handshakes.append({'channel':'b','addr':q['addr'],'id':0,'resp':q['resp'],'cycle':cycle})
            self.write=None; self.counts['b']+=1
        if 'ar' in hs:
            p=hs['ar']; address_check(p,True)
            require(p['id'] not in self.reads,'CNEM-14 read outstanding bound')
            if p['id']==0: require(self.aw is None and self.w is None and self.write is None,'CNEM-14 data outstanding bound')
            data,resp=snapshot_read(self.mem,p)
            selected=self.response(p,'r')
            if selected: data,resp=0,selected
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
            resp=self.response(a,'b') or (0 if BASE<=a['addr']<END else 3)
            ret_value=None; ret_bytes={}
            if resp==0:
                require(changed<=WRITE_BYTES,'CNEM-28 illegal write footprint/code/guard')
                require(self.halt is None,'CNEM-22 late data write')
                if changed & set(range(self.config['ret'],self.config['ret']+4)):
                    require(not self.magic,'CNEM-21/31 return store after final magic')
                if changed & set(range(RECORD,RECORD+64)):
                    require(not self.magic,'CNEM-20 record write after magic')
                    if RECORD in changed:
                        require(set(range(RECORD,RECORD+4))<=changed,'partial magic')
                        require(NEGATIVE_RECORD_BYTES-set(range(RECORD,RECORD+4))<=self.written,'CNEM-21 early trap magic')
                        require(len(self.error_handshakes)==1,'CNEM-21 trap magic before selected error completion')
                        require(self.return_bytes==set(range(4)),'CNEM-21/31 magic before completed handler return stores')
                        self.magic=True
                for addr in changed: self.mem[addr-BASE]=(w['data']>>(8*(addr&15)))&255
                ret=self.config['ret']
                if changed & set(range(ret,ret+4)):
                    ret_bytes={address-ret:self.mem[address-BASE] for address in changed if ret<=address<ret+4}
                    if set(ret_bytes)==set(range(4)):
                        ret_value=struct.unpack_from('<I',self.mem,ret-BASE)[0]
                        if ret_value==1:
                            require(self.sentinel_b is not None,'CNEM-31 missing/reversed startup sentinel')
                            require(self.sentinel_b<min(a['cycle'],w['cycle']),'CNEM-31 sentinel B must precede first return half')
                        self.ret_values.append(ret_value)
                if a['addr'] in (PROBE+1,PROBE+6,PROBE+12): self.probe_stores.add((a['addr'],a['size']))
            self.write={'cycle':max(a['cycle'],w['cycle']),'bytes':changed,'resp':resp,'addr':a['addr'],'ret_value':ret_value,'ret_bytes':ret_bytes,'first_half':min(a['cycle'],w['cycle'])}
            self.aw=self.w=None
        for q in self.reads.values(): require(cycle<q['cycle']+256,'CNEM-19 R deadline')
        if self.write: require(cycle<self.write['cycle']+256,'CNEM-19 B deadline')
        for q in (self.aw,self.w):
            if q: require(cycle<q['cycle']+64,'CNEM-19 unmatched half deadline')
        if self.release is not None and self.halt is None:
            require(cycle-self.release<=1000000,'CNEM-31 late terminal edge')
            if status=={'halted':1,'fault':0,'wfi':0}:
                try:
                    self.accept()
                except AssertionError as exc:
                    self.pending_terminal_reason=str(exc)
                else:
                    self.halt=cycle; self.terminal_mem=bytes(self.mem)
            if self.halt is None:
                require(cycle-self.release<1000000,'CNEM-31 terminal deadline: '+str(self.pending_terminal_reason))
    def observe_responder(self,cycle,memory,commit_count):
        """Observe actual responder effects independently from predicted bus bytes."""
        require(bytes(memory)==bytes(self.mem),'Independent responder/scoreboard aperture equality')
        if self.halt is not None:
            require(cycle==self.halt+len(self.responder_observation_cycles),'CNEM-31 consecutive responder observations')
            self.responder_observation_cycles.append(cycle)
            if cycle==self.halt:self.terminal_commits=commit_count
            else:
                require(bytes(memory)==self.terminal_mem,'CNEM-31 responder aperture changed')
                require(commit_count==self.terminal_commits,'CNEM-31 responder write commit after terminal')
    def finish(self):
        require(self.halt is not None and len(self.post_halt_observations)==32,'CNEM-31 incomplete terminal observation')
        require(len(self.responder_observation_cycles)==33,'CNEM-31 missing independent responder observation')
        self.accept()
    def response(self,p,channel):
        kind=self.config['error_kind'];target=self.config['fault_address']
        chosen=(p['addr']==target and channel==('b' if kind=='store' else 'r')
                and p['id']==(1 if kind=='fetch' else 0))
        if chosen and not self.target_operations:
            require(p['size']==(4 if kind=='fetch' else 2),'CNEM-23 targeted operation size')
            self.target_operations+=1
            if kind=='unmapped':return 0  # CNEM-25 decode, not response substitution.
            self.substitutions+=1
            return self.config['error_response']
        return 0
    def accept(self):
        require(self.aw is None and self.w is None and self.write is None and 0 not in self.reads,'CNEM-21 incomplete trap data responses')
        require(self.target_operations==1 and len(self.error_handshakes)==1,'CNEM-23/25 exactly one selected error response')
        require(self.substitutions==(0 if self.config['error_kind']=='unmapped' else 1),'CNEM-23 substitution count')
        error=self.error_handshakes[0]
        require(error['addr']==self.config['fault_address'] and error['resp']==self.config['error_response'],'CNEM-23 wrong injected error')
        require(NEGATIVE_RECORD_BYTES<=self.written,'CNEM-21 mandatory negative record write coverage')
        require(set(range(BASE+0x18004,BASE+0x18008))<=self.read_bytes,'CNEM-21 live descriptor run_id read')
        words=[0x434e454d,1,self.config['run_id'],1,0,0,0,1,
               self.config['expected_mcause'],self.config['expected_mepc'],self.config['expected_mtval'],1,0,0,0,0]
        expected=struct.pack('<16I',*words);got=bytes(self.mem[RECORD-BASE:RECORD-BASE+64])
        require(got==expected,f'CNEM-21/24 trap record expected={expected.hex()} observed={got.hex()}')
        require(self.sentinel_b is not None and self.return_bytes==set(range(4)),'CNEM-31 completed sentinel/return byte evidence')
        require(struct.unpack_from('<I',self.mem,self.config['ret']-BASE)[0]==1,'CNEM-21 return slot equality')
        for a in GUARDS:require(self.mem[a-BASE:a-BASE+16]==b'\xa5'*16,'CNEM-28 guard preservation')
    def summary(self):
        return {'counts':dict(self.counts),'record_bytes':len(NEGATIVE_RECORD_BYTES&self.written),
                'ret_stores':self.ret_values,'error_handshakes':self.error_handshakes,
                'response_substitutions':self.substitutions,'selected_target_operations':self.target_operations,'release_cycle':self.release,'halt_cycle':self.halt,
                'return_write_events':self.ret_write_events,'sentinel_B_cycle':self.sentinel_b,'completed_return_bytes':sorted(self.return_bytes),
                'checked_post_terminal_cycles':len(self.post_halt_observations),'completed_ret_stores':self.ret_completed,
                'startup_sentinel_observed':bool(self.ret_values and self.ret_values[0]==0x0badd00d),
                'post_terminal_observations':self.post_halt_observations,'terminal_pending_reason':self.pending_terminal_reason}
