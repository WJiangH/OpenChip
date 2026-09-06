"""Export local architecture review drawings as editable VSDX shapes.

Uses Visio OPC/XML, shape geometry, named connection points and Connect records.
The architecture remains a candidate; endpoint names are proposed contracts.
"""
from pathlib import Path
import json
import math
import zipfile
import xml.etree.ElementTree as ET
from PIL import ImageFont

HERE=Path(__file__).resolve().parent
OUT=HERE/'review-v0.2'
OUT.mkdir(exist_ok=True)
DATA=json.loads((HERE/'diagram-data.json').read_text())
NS='http://schemas.microsoft.com/office/visio/2012/main'
REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
VREL='http://schemas.microsoft.com/visio/2010/relationships'
PKG='http://schemas.openxmlformats.org/package/2006/relationships'
CT='http://schemas.openxmlformats.org/package/2006/content-types'
ET.register_namespace('',NS);ET.register_namespace('r',REL)
S=120.0
PW,PH=16.5354,11.6929
OX,OY=0.35,0.25
COLORS={'control':('#EDF3FB','#3468A0'),'data':('#EAF5EF','#28734E'),
        'security':('#F4EFFA','#785297'),'platform':('#FFF4E5','#A76A22'),
        'neutral':('#F3F5F7','#52606D')}
PREFIX=['SOC','NPU','BOOT','CR']
LABEL_FONT=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',14)


def el(parent,name,**attrs):
    return ET.SubElement(parent,f'{{{NS}}}{name}',{k:str(v) for k,v in attrs.items()})


def cell(parent,n,v,f=None):
    c=el(parent,'Cell',N=n,V=v)
    if f is not None:c.set('F',f)
    return c


def ser(root):
    result=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    # Some Visio importers require default namespaces on OPC metadata parts.
    if root.tag.startswith('{'+PKG+'}') or root.tag.startswith('{'+CT+'}'):
        result=result.replace(b'ns0:',b'').replace(b'xmlns:ns0=',b'xmlns=')
    return result


def relationships(items):
    r=ET.Element(f'{{{PKG}}}Relationships')
    for i,t,target in items:
        ET.SubElement(r,f'{{{PKG}}}Relationship',Id=i,Type=t,Target=target)
    return ser(r)


def styling(sh,fill,stroke,textsize=11,bold=False,dashed=False,textonly=False,group=False):
    cell(sh,'LineColor',stroke);cell(sh,'LineWeight',0.012)
    cell(sh,'LinePattern',0 if textonly else (2 if dashed else 1))
    cell(sh,'FillForegnd',fill);cell(sh,'FillPattern',0 if textonly or group else 1)
    cell(sh,'VerticalAlign',0 if group else 1)
    for k in ['LeftMargin','RightMargin','TopMargin','BottomMargin']:cell(sh,k,0.035)
    sec=el(sh,'Section',N='Character');row=el(sec,'Row',IX=0)
    cell(row,'Font',0);cell(row,'Size',textsize/72);cell(row,'Color','#182B3A');cell(row,'Style',1 if bold else 0)
    sec=el(sh,'Section',N='Paragraph');row=el(sec,'Row',IX=0)
    cell(row,'HorzAlign',0 if group else 1)


def box(sh,x,y,w,h):
    x=OX+x/S;y=PH-OY-(y+h)/S;w/=S;h/=S
    for k,v in [('PinX',x+w/2),('PinY',y+h/2),('Width',w),('Height',h),('LocPinX',w/2),('LocPinY',h/2),('Angle',0)]:cell(sh,k,v)
    sec=el(sh,'Section',N='Geometry',IX=0)
    for i,(a,b) in enumerate([(0,0),(w,0),(w,h),(0,h),(0,0)]):
        row=el(sec,'Row',T='MoveTo' if i==0 else 'LineTo',IX=i+1)
        cell(row,'X',a);cell(row,'Y',b)


def point(x,y):return OX+x/S, PH-OY-y/S


def shape_data(sh,fields):
    sec=el(sh,'Section',N='Property')
    for i,(k,v) in enumerate(fields.items()):
        r=el(sec,'Row',IX=i,N=k)
        cell(r,'Label',k);cell(r,'Type',0);cell(r,'Value',v)


def textshape(shapes,ident,x,y,w,h,text,size=10,bold=False,opaque=False):
    sh=el(shapes,'Shape',ID=ident,NameU=f'Text.{ident}',Type='Shape',LineStyle=0,FillStyle=0,TextStyle=0)
    box(sh,x,y,w,h);styling(sh,'#FFFFFF','#FFFFFF',size,bold,textonly=True)
    if opaque:
        for c in sh.findall(f'{{{NS}}}Cell'):
            if c.get('N')=='FillPattern':c.set('V','1')
    el(sh,'Text').text=text


def page(d,pi):
    r=ET.Element(f'{{{NS}}}PageContents')
    shapes=el(r,'Shapes');connects=el(r,'Connects')
    nodes={n['id']:n for n in d['nodes']}
    idmap={n['id']:i+1 for i,n in enumerate(d['nodes'])}
    ports={n['id']:[] for n in d['nodes']}
    for ei,e in enumerate(d['edges']):
        for which,idx in [('source',0),('target',-1)]:
            n=nodes[e[which]];x,y=e['points'][idx]
            ports[n['id']].append((ei,which,(x-n['x'])/S,(n['y']+n['h']-y)/S))
    portmap={}
    for n in d['nodes']:
        sh=el(shapes,'Shape',ID=idmap[n['id']],NameU=n['id'],Type='Shape',LineStyle=0,FillStyle=0,TextStyle=0)
        box(sh,n['x'],n['y'],n['w'],n['h'])
        fill,stroke=COLORS[n['kind']]
        styling(sh,fill,stroke,10.4,group=n['group'])
        el(sh,'Text').text='\n'.join(n['lines'])
        shape_data(sh,{'BlockID':n['id'],'Status':'CANDIDATE - NOT FROZEN','Owner':'TBD by block work item'})
        if ports[n['id']]:
            sec=el(sh,'Section',N='Connection')
            for ix,(ei,which,x,y) in enumerate(ports[n['id']]):
                rr=el(sec,'Row',IX=ix)
                cell(rr,'X',x,f'Width*{x/(n["w"]/S):.9g}')
                cell(rr,'Y',y,f'Height*{y/(n["h"]/S):.9g}')
                cell(rr,'DirX',0);cell(rr,'DirY',0);cell(rr,'Type',0)
                portmap[ei,which]=ix
    records=[]
    for ei,e in enumerate(d['edges']):
        ident=len(d['nodes'])+ei+1
        eid=f'{PREFIX[pi]}-{ei+1:02d}'
        sh=el(shapes,'Shape',ID=ident,NameU=eid,Type='Shape',LineStyle=0,FillStyle=0,TextStyle=0)
        coords=[point(*p) for p in e['points']]
        bx,by=coords[0];ex,ey=coords[-1]
        dx,dy=ex-bx,ey-by;length=math.hypot(dx,dy);angle=math.atan2(dy,dx)
        assert length>0
        for k,v,f in [('BeginX',bx,None),('BeginY',by,None),('EndX',ex,None),('EndY',ey,None),
                      ('PinX',(bx+ex)/2,'(BeginX+EndX)/2'),('PinY',(by+ey)/2,'(BeginY+EndY)/2'),
                      ('Width',length,'SQRT((EndX-BeginX)^2+(EndY-BeginY)^2)'),('Height',0.001,None),
                      ('LocPinX',length/2,'Width/2'),('LocPinY',0,None),('Angle',angle,'ATAN2(EndY-BeginY,EndX-BeginX)'),('OneD',1,None)]:cell(sh,k,v,f)
        styling(sh,'#FFFFFF',COLORS[e['kind']][1],9,dashed=e['dashed'],textonly=False,group=True)
        cell(sh,'BeginArrow',4 if e['both'] else 0);cell(sh,'EndArrow',4)
        cell(sh,'BeginArrowSize',1);cell(sh,'EndArrowSize',1)
        sec=el(sh,'Section',N='Geometry',IX=0);cell(sec,'NoFill',1)
        for j,(px,py) in enumerate(coords):
            lx=(px-bx)*math.cos(angle)+(py-by)*math.sin(angle)
            ly=-(px-bx)*math.sin(angle)+(py-by)*math.cos(angle)
            rr=el(sec,'Row',T='MoveTo' if j==0 else 'LineTo',IX=j+1)
            cell(rr,'X',lx,f'Width*{lx/length:.12g}');cell(rr,'Y',ly)
        for which,end in [('source','Begin'),('target','End')]:
            sid=idmap[e[which]];ix=portmap[ei,which]+1
            for axis in ['X','Y']:
                for cc in sh.findall(f'{{{NS}}}Cell'):
                    if cc.get('N')==end+axis:
                        cc.set('F',f'PAR(PNT(Sheet.{sid}!Connections.X{ix},Sheet.{sid}!Connections.Y{ix}))')
            el(connects,'Connect',FromSheet=ident,FromCell=end+'X',ToSheet=sid,ToCell=f'Connections.X{ix}')
        semantics='FLOW (not hardware port)' if pi==2 else ('CLOCK/RESET bundle' if pi==3 else 'logical interface')
        width='TBD - no implementation release'
        if pi==0 and ei==0:width='D=32 candidate; address/ID/adaptation TBD'
        if 'IRQ' in e['label'] or e['label']=='done / fault':width='event bundle; source count/polarity TBD'
        if pi==3 and e['label']=='soc_clk':width='1-bit clock; frequency TBD'
        role='Source/target roles require contract; arrows show traffic, not AXI role'
        if e['label'].startswith('AXI'):
            role='AXI endpoint roles must be split into initiator/target ports in ICD'
        rec=dict(id=eid,view=d['name'],source=e['source'],target=e['target'],label=e['label'],
                 kind=semantics,width=width,clock='soc_clk candidate; PHY/external exceptions TBD',
                 reset='reset owner/polarity/order TBD by block',role=role,status='CANDIDATE',
                 obligation='Protocol/functional/negative/reset tests; IDs assigned by independent DV')
        records.append(rec)
        shape_data(sh,{'InterfaceID':eid,'SourceBlock':e['source'],'TargetBlock':e['target'],
                       'InterfaceType':semantics,'WidthStatus':width,'Status':'CANDIDATE - NOT FROZEN'})
    tid=1000
    textshape(shapes,tid,50,16,1680,43,d['title'],18,True);tid+=1
    textshape(shapes,tid,50,60,1680,34,'OpenChip architecture review | Rev 0.2 | '+d['subtitle'].replace('v0.1','v0.2'),10);tid+=1
    for note in d['notes']:
        textshape(shapes,tid,note['x'],note['y']-19,1700,30,note['text'],9);tid+=1
    # Put labels in clear space; never mask a port or a wire with a white box.
    occupied=[]
    for note in d['notes']:
        occupied.append((note['x'],note['y']-20,note['x']+1700,note['y']+15))
    for n in d['nodes']:
        occupied.append((n['x']-3,n['y']-3,n['x']+n['w']+3,
                         n['y']+(38 if n['group'] else n['h'])+3))
    for ee in d['edges']:
        for (x0,y0),(x1,y1) in zip(ee['points'],ee['points'][1:]):
            occupied.append((min(x0,x1)-2,min(y0,y1)-2,max(x0,x1)+2,max(y0,y1)+2))
    def overlap(a,b):return a[0]<b[2] and a[2]>b[0] and a[1]<b[3] and a[3]>b[1]
    offsets=sorted([(dx,dy) for dx in range(-180,181,15) for dy in range(-120,121,15)],
                   key=lambda t:t[0]*t[0]+t[1]*t[1])
    for ei,e in enumerate(d['edges']):
        x,y=e['label_at'];eid=f'{PREFIX[pi]}-{ei+1:02d}'
        if pi==0 and ei==7:x,y=1460,695
        if pi==0 and ei==9:x,y=1220,702
        w=max(LABEL_FONT.getlength(e['label']),LABEL_FONT.getlength(eid))*(8.5*S/72/14)+12
        chosen=None
        for dx,dy in offsets:
            b=(x-w/2+dx,y-27+dy,x+w/2+dx,y+8+dy)
            if b[0]>=30 and b[1]>=110 and b[2]<=1775 and b[3]<=d['height']-70 and not any(overlap(b,z) for z in occupied):
                chosen=b;break
        assert chosen is not None,(pi,eid)
        occupied.append(chosen)
        textshape(shapes,tid,chosen[0],chosen[1],w,35,f'{eid}\n{e["label"]}',8.5);tid+=1
    # Separate A3 review title block below the drawing area.
    sh=el(shapes,'Shape',ID=1900,NameU='ReviewTitleBlock',Type='Shape',LineStyle=0,FillStyle=0,TextStyle=0)
    box(sh,1120,1228,720,94);styling(sh,'#FFFFFF','#52606D',10)
    el(sh,'Text').text=(f'OPENCHIP  |  {PREFIX[pi]}  |  Sheet {pi+1}/4  |  Rev 0.2\n'
                       '2026-09-05  |  Chief architect  |  CANDIDATE\n'
                       'LOCAL ONLY  |  NOT RELEASED FOR IMPLEMENTATION')
    return ser(r),records


def main():
    parts={}
    parts['_rels/.rels']=relationships([('rId1',VREL+'/document','visio/document.xml')])
    doc=ET.Element(f'{{{NS}}}VisioDocument')
    settings=el(doc,'DocumentSettings',TopPage=0,DefaultTextStyle=0,DefaultLineStyle=0,DefaultFillStyle=0,DefaultGuideStyle=0)
    colors=el(doc,'Colors');el(colors,'ColorEntry',IX=0,RGB='#000000');el(colors,'ColorEntry',IX=1,RGB='#FFFFFF')
    faces=el(doc,'FaceNames');el(faces,'FaceName',NameU='Arial',UnicodeRanges='-536859905 -1073711037 9 0',CharSets='0 0',Panose='2 11 6 4 2 2 2 2 2 4',Flags=325)
    styles=el(doc,'StyleSheets');st=el(styles,'StyleSheet',ID=0,NameU='No Style',Name='No Style')
    styling(st,'#FFFFFF','#000000',10)
    parts['visio/document.xml']=ser(doc)
    parts['visio/_rels/document.xml.rels']=relationships([('rId1',VREL+'/pages','pages/pages.xml')])
    pages=ET.Element(f'{{{NS}}}Pages');rels=[];all_records=[]
    for pi,d in enumerate(DATA):
        p=el(pages,'Page',ID=pi,Name=d['name'],NameU=d['name'])
        ps=el(p,'PageSheet',LineStyle=0,FillStyle=0,TextStyle=0)
        for n,v in [('PageWidth',PW),('PageHeight',PH),('PageScale',1),('DrawingScale',1),('DrawingSizeType',0),('DrawingScaleType',0)]:cell(ps,n,v)
        el(p,'Rel',**{f'{{{REL}}}id':f'rId{pi+1}'})
        xml,records=page(d,pi);all_records.extend(records)
        parts[f'visio/pages/page{pi+1}.xml']=xml
        rels.append((f'rId{pi+1}',VREL+'/page',f'page{pi+1}.xml'))
    parts['visio/pages/pages.xml']=ser(pages)
    parts['visio/pages/_rels/pages.xml.rels']=relationships(rels)
    types=ET.Element(f'{{{CT}}}Types')
    ET.SubElement(types,f'{{{CT}}}Default',Extension='rels',ContentType='application/vnd.openxmlformats-package.relationships+xml')
    ET.SubElement(types,f'{{{CT}}}Default',Extension='xml',ContentType='application/xml')
    for name,mime in [('visio/document.xml','drawing.main'),('visio/pages/pages.xml','pages'),
                      *[(f'visio/pages/page{i+1}.xml','page') for i in range(len(DATA))]]:
        ET.SubElement(types,f'{{{CT}}}Override',PartName='/'+name,ContentType='application/vnd.ms-visio.'+mime+'+xml')
    parts['[Content_Types].xml']=ser(types)
    out=OUT/'openchip-architecture-review-v0.2.vsdx'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name,content in parts.items():z.writestr(name,content)
    (OUT/'interface-register.json').write_text(json.dumps(all_records,indent=2)+'\n')
    lines=['# OpenChip 接口连接登记册 - Rev 0.2','',
           '状态：架构候选；本登记册尚未完成接口控制文件（ICD）的冻结条件。',
           '编号对应 Visio 图中的连接与 Shape Data。BOOT-* 是流程步骤，不是硬件端口；其余也可能表示接口束。','',
           '## AXI 端点角色裁决（候选）','',
           '- CPU、NPU DMA 是系统互连的 initiator；SRAM、外存控制器、ROM、外设桥和 NPU CSR 是 target。',
           '- CPU 经适配进入 AXI4；NPU CSR 前的 AXI4-to-Lite 适配必须成为独立的可验证交付物。',
           '- 安全域 SOC-02 图线是接口束：安全域 initiator 到系统 target，以及系统获授权 initiator 到安全域 mailbox target；下发规格前必须拆成两套接口。',
           '- M/S 角色不由双向箭头决定；箭头包含请求和返回流量。',
           '- 图中信号名称是候选端点，不是从现有 RTL 提取的端口，不能据此宣称连线已正确实现。','',
           '## 逐连接清单','',
           '| ID | 图/类型 | 来源 | 目标 | 接口或事件 | 位宽状态 |',
           '|---|---|---|---|---|---|']
    for r in all_records:
        lines.append(f"| {r['id']} | {r['kind']} | `{r['source']}` | `{r['target']}` | {r['label']} | {r['width']} |")
    lines += ['', '## 下发 RTL/DV 前的必填字段','',
              '- 单独的端口名、方向、协议版本、数据/地址/ID/USER 宽度及转换。',
              '- burst、在途事务、排序、对齐、字节使能、错误、超时、取消与复位中事务处理。',
              '- 地址窗口、访问身份、默认权限与 DMA 可访问范围。',
              '- 时钟频率/来源、复位极性/同步性/顺序、CDC/RDC、必要电源隔离和 retention。',
              '- block owner、对应规格版本、独立 DV 测试/属性 ID、变更影响列表。',
              '- 未定项由架构师裁决，不允许实现 agent 自行补齐接口语义。','']
    (OUT/'interface-register.md').write_text('\n'.join(lines))
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        for n in z.namelist():ET.fromstring(z.read(n))
        count=0
        for i in range(4):
            root=ET.fromstring(z.read(f'visio/pages/page{i+1}.xml'))
            ids={s.get('ID') for s in root.findall(f'.//{{{NS}}}Shape')}
            for c in root.findall(f'.//{{{NS}}}Connect'):
                assert c.get('FromSheet') in ids and c.get('ToSheet') in ids
                count+=1
        assert count==110
    print('VSDX structural check: PASS; 4 pages; 55 editable connection shapes; 110 endpoint attachment records; no embedded diagram bitmaps.')


if __name__=='__main__':main()
