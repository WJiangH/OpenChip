"""CNEM-23/25 error substitution and CNEM-26/27 coordinated-abort environment."""
from responder import Responder
from checker import BASE,END,require
class FaultResponder(Responder):
    def __init__(self,image,config):
        super().__init__(image,config['schedule'],config['seed']);self.config=config;self.injected=[];self.write_commits=[]
    def error_for(self,p,channel,cycle):
        kind=self.config['error_kind']
        if kind=='unmapped':return 0  # Decode creates DECERR without an injected response.
        expected_channel='b' if kind=='store' else 'r'
        expected_id=1 if kind=='fetch' else 0
        if (not self.injected and channel==expected_channel and p['addr']==self.config['fault_address'] and p['id']==expected_id):
            response=self.config['error_response']
            self.injected.append({'channel':channel,'request_cycle':cycle,'address':p['addr'],'id':p['id'],'response':response})
            return response
        return 0
    def advance(self,cycle,snapshot):
        for k in self.cool:
            if self.cool[k]:self.cool[k]-=1
            else:self.cool[k]=0 if self.schedule=='P0' else self.rng[k].randint(0,7)
        hs={k:s['p'] for k,s in snapshot.items() if s['valid'] and s['ready']}
        if 'r' in hs:self.active_r=None
        if 'b' in hs:self.active_b=None
        if 'ar' in hs:
            p=hs['ar'];error=self.error_for(p,'r',cycle)
            if not BASE<=p['addr']<END:error=3
            data=0
            if not error:
                raw=self.memory[p['addr']-BASE:p['addr']-BASE+(1<<p['size'])]
                data=int.from_bytes(raw,'little')<<((p['addr']&15)*8)
            self.ar.append({'id':p['id'],'due':cycle+self.delay('r'),'p':dict(id=p['id'],data=data,resp=error,last=1)})
        if 'aw' in hs:self.aw.append(hs['aw'])
        if 'w' in hs:self.w.append(hs['w'])
        if self.aw and self.w:
            a=self.aw.pop(0);w=self.w.pop(0);error=self.error_for(a,'b',cycle)
            if not BASE<=a['addr']<END:error=3
            if not error:
                self.write_commits.append({'cycle':cycle,'address':a['addr'],'strobe':w['strb']})
                base=(a['addr']&~15)-BASE;data=w['data'].to_bytes(16,'little')
                for lane in range(16):
                    if w['strb']&(1<<lane):self.memory[base+lane]=data[lane]
            self.b.append({'due':cycle+self.delay('b'),'p':dict(id=a['id'],resp=error)})
class AbortResponder(Responder):
    def __init__(self,image,config):
        super().__init__(image,'P0',config['seed']);self.mode=config['reset_kind']
    def outputs(self,cycle):
        outputs=super().outputs(cycle)
        if self.mode=='ar':outputs['r']={'valid':0,'p':dict(data=0,id=0,resp=0,last=0)}
        if self.mode=='aw_only':outputs['w']['ready']=0
        return outputs
    def purge(self):
        self.ar.clear();self.aw.clear();self.w.clear();self.b.clear()
        self.active_r=self.active_b=None

def abort_epoch(checker,responder,kind,entry,ret):
    """Validate selected pending witness before canceling old-epoch obligations."""
    require(kind in ('ar','aw_only'),'CNEM-27 unsupported reset selection')
    require(checker.release is not None,'CNEM-27 abort before release')
    if kind=='ar':
        q=checker.reads.get(1)
        require(q is not None and q['addr']==(entry&~15),'CNEM-27 required pending entry fetch')
        witness={'kind':'AR_WITHOUT_R','request':dict(q)}
    else:
        require(checker.aw is not None and checker.w is None and checker.write is None,'CNEM-27 AW-only witness')
        require(checker.aw['addr']==ret,'CNEM-27 selected startup return AW')
        witness={'kind':'AW_WITHOUT_W','request':dict(checker.aw)}
    witness['release_cycle']=checker.release
    witness['canceled_reads']={str(k):dict(v) for k,v in checker.reads.items()}
    witness['canceled_aw']=checker.aw;witness['canceled_w']=checker.w
    responder.purge()
    checker.reads.clear();checker.aw=checker.w=checker.write=None;checker.prev.clear();checker.release=None
    return witness
