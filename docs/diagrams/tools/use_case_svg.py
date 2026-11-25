import html
W,H=1900,1260
FX0,FX1=200,1640
bands=[
 dict(key='blue',y=205,h=200,fill='#DCEBFF',fill2='#EEF5FF',line='#1F5FBF',pill='#0B4DA8',name='Discovery',icon='search',
      desc=['find relevant','laptops and compare','options across shops'],
      uc='UC1 – Find &\nCompare Laptop Offers',
      inc=['Search and filter laptops','Sort results','Compare up to three laptops','View offers with source, freshness']),
 dict(key='orange',y=420,h=330,fill='#FFE4CF',fill2='#FFF2E6',line='#E07A1F',pill='#D9650B',name='Analysis & Advice',icon='bars',
      desc=['understand whether','the current offer is','genuinely good, and','what to do about it'],
      uc='UC2 – Assess Price\n& Get Advice',
      inc=['View 30-day history, reference','Inspect discount evidence','View stored 7-day forecast and age','Get Buy Now / Wait advice']),
 dict(key='green',y=765,h=200,fill='#DDF5DD',fill2='#EEFAEE',line='#2E8B2E',pill='#1F7A1F',name='Data Maintenance',icon='db',
      desc=['keep dated,','attributable price','observations'],
      uc='UC3 – Maintain\nPrice Data',
      inc=['Fetch approved batch','Validate and normalize records','Upsert without duplicates','Publish price.changed, queue job']),
 dict(key='purple',y=980,h=200,fill='#EADFFB',fill2='#F5EEFD',line='#7B3FC6',pill='#6A2DB8',name='Energy Adaptation',icon='bolt',
      desc=['react to carbon','intensity, electricity','price and renewables'],
      uc='UC4 – Adapt to Carbon &\nEnergy-Price Conditions',
      inc=['Sense carbon, price, renewable','Decide mode GREEN/AMBER/RED','Change behaviour (jobs, AI, batches)','Relocate flexible workloads']),
]
o=[]
a=o.append
a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="Helvetica, Arial, sans-serif">')
a('''<defs>
<marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#222"/></marker>
<style>.t{font-weight:700;fill:#111}.d{font-style:italic;fill:#333;font-size:17px}.st{font-size:12px;fill:#222;font-style:normal}.lbl{font-size:12px;font-weight:700;fill:#111}</style>
</defs>''')
a(f'<rect width="{W}" height="{H}" fill="#fff"/>')
a(f'<text x="{W/2}" y="52" text-anchor="middle" font-size="46" font-weight="800" fill="#0E0E3A">Smart Shopping – Use Case Diagram</text>')
a(f'<rect x="{W/2-260}" y="72" width="520" height="40" rx="20" fill="#E6E3FA"/><text x="{W/2}" y="99" text-anchor="middle" font-size="22" fill="#222">AACC course project · Laptop price advisor</text>')
a(f'<line x1="{W/2-520}" y1="92" x2="{W/2-300}" y2="92" stroke="#9A8CF0" stroke-width="3"/><line x1="{W/2+300}" y1="92" x2="{W/2+520}" y2="92" stroke="#9A8CF0" stroke-width="3"/>')
fy1=1205
a(f'<rect x="{FX0}" y="140" width="{FX1-FX0}" height="{fy1-140}" rx="22" fill="#F7F7FD" stroke="#7A7A9A" stroke-width="3"/>')
a(f'<path d="M{FX0},162 a22,22 0 0 1 22,-22 h{FX1-FX0-44} a22,22 0 0 1 22,22 v38 h-{FX1-FX0} z" fill="#DAD8F2"/>')
a(f'<text x="{(FX0+FX1)/2}" y="185" text-anchor="middle" font-size="32" font-weight="700" fill="#111">Smart Shopping System</text>')
# cart icon
a('<g transform="translate(655,150)" fill="none" stroke="#111" stroke-width="3"><path d="M0,5 h8 l7,22 h24 l5,-16 h-33"/><circle cx="18" cy="35" r="3"/><circle cx="36" cy="35" r="3"/></g>')
def icon(kind,x,y):
    s='<g fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round">'
    if kind=='search': s+=f'<circle cx="{x+8}" cy="{y+8}" r="8"/><line x1="{x+14}" y1="{y+14}" x2="{x+22}" y2="{y+22}"/>'
    if kind=='bars': s+=f'<line x1="{x+3}" y1="{y+22}" x2="{x+3}" y2="{y+14}"/><line x1="{x+12}" y1="{y+22}" x2="{x+12}" y2="{y+4}"/><line x1="{x+21}" y1="{y+22}" x2="{x+21}" y2="{y+10}"/>'
    if kind=='db': s+=f'<ellipse cx="{x+12}" cy="{y+5}" rx="10" ry="4"/><path d="M{x+2},{y+5} v14 a10,4 0 0 0 20,0 v-14"/><path d="M{x+2},{y+12} a10,4 0 0 0 20,0"/>'
    if kind=='bolt': s+=f'<path d="M{x+14},{y} l-10,13 h8 l-3,10 l11,-14 h-8 z" fill="#fff"/>'
    return s+'</g>'
def lines(txt,x,y,lh,size,anchor='middle',cls='t'):
    return ''.join(f'<text x="{x}" y="{y+i*lh}" text-anchor="{anchor}" font-size="{size}" class="{cls}">{html.escape(l)}</text>' for i,l in enumerate(txt.split('\n')))
pos={}
band_by={b['key']:b for b in bands}
body=[]
for b in bands:
    y,h=b['y'],b['h']
    body.append(f'<rect x="{FX0+20}" y="{y}" width="{FX1-FX0-40}" height="{h}" rx="20" fill="{b["fill"]}"/>')
    n=4; step=44; top=y+10
    ucx=860; ucy=top+n*step/2
    pos[b['key']]=(ucx,ucy)
over=[]
for b in bands:
    y,h=b['y'],b['h']; top=y+10; step=44; ucx,ucy=pos[b['key']]
    over.append(f'<rect x="258" y="{y+10}" width="250" height="40" rx="20" fill="{b["pill"]}"/>'+icon(b['icon'],275,y+18)+f'<text x="312" y="{y+37}" font-size="21" font-weight="700" fill="#fff">{html.escape(b["name"])}</text>')
    over.append(''.join(f'<text x="278" y="{y+75+i*22}" class="d" stroke="{b["fill"]}" stroke-width="5" paint-order="stroke">{html.escape(l)}</text>' for i,l in enumerate(b['desc'])))
    over.append(f'<line x1="530" y1="{y+20}" x2="530" y2="{y+h-20}" stroke="{b["line"]}" stroke-opacity=".35"/>')
    ex=1420
    for i,t in enumerate(b['inc']):
        cy=top+step*i+step/2
        sy=ucy+(i-1.5)*9
        over.append(f'<path d="M{ucx+168},{sy} C{ucx+280},{sy} {ex-300},{cy} {ex-188},{cy}" fill="none" stroke="#222" stroke-width="1.6" stroke-dasharray="6 4" marker-end="url(#ah)"/>')
        over.append(f'<text x="1135" y="{cy-5}" class="lbl" text-anchor="middle" stroke="{b["fill"]}" stroke-width="4" paint-order="stroke">«include»</text>')
        over.append(f'<ellipse cx="{ex}" cy="{cy}" rx="186" ry="17" fill="{b["fill2"]}" stroke="{b["line"]}" stroke-width="2.4"/><text x="{ex}" y="{cy+5}" text-anchor="middle" font-size="15" font-weight="700" fill="#111">{html.escape(t)}</text>')
    over.append(f'<ellipse cx="{ucx}" cy="{ucy}" rx="175" ry="62" fill="{b["fill2"]}" stroke="{b["line"]}" stroke-width="3.2"/>')
    over.append(lines(b['uc'],ucx,ucy-4,24,21))
ob=band_by['orange']; ux,uy=pos['orange']
ey=ob['y']+ob['h']-62
AIx,Wx=720,1150
for ex,t in ((AIx,'UC2 extension\nExplain the advice (AI assistant)'),(Wx,'UC2 extension\nWatch a price (in-app alerts)')):
    over.append(f'<path d="M{ex},{ey-30} L{ux+(ex-ux)*0.4},{uy+60}" stroke="#222" stroke-width="1.6" stroke-dasharray="6 4" marker-end="url(#ah)" fill="none"/>')
    over.append(f'<text x="{ex+(ux-ex)*0.25+(16 if ex>ux else -16)}" y="{(ey-30+uy+60)/2}" class="lbl" text-anchor="{"start" if ex>ux else "end"}" stroke="{ob["fill"]}" stroke-width="4" paint-order="stroke">«extend»</text>')
    over.append(f'<ellipse cx="{ex}" cy="{ey}" rx="200" ry="30" fill="{ob["fill2"]}" stroke="{ob["line"]}" stroke-width="2.4" stroke-dasharray="7 4"/>'+lines(t,ex,ey-4,19,15))
def actor(x,y,label,stereo=None,k=0.7):
    r=26*k
    s=f'<g stroke="#222" stroke-width="2.6" fill="#E4E4F4"><circle cx="{x}" cy="{y}" r="{r}"/><line x1="{x}" y1="{y+r}" x2="{x}" y2="{y+85*k}"/><line x1="{x-42*k}" y1="{y+48*k}" x2="{x+42*k}" y2="{y+48*k}"/><line x1="{x}" y1="{y+85*k}" x2="{x-34*k}" y2="{y+128*k}"/><line x1="{x}" y1="{y+85*k}" x2="{x+34*k}" y2="{y+128*k}"/></g>'
    ly=y+128*k+24
    if stereo: s+=f'<text x="{x}" y="{y-r-8}" text-anchor="middle" font-size="14" font-style="italic" fill="#333">«{stereo}»</text>'
    for i,l in enumerate(label.split('\n')):
        s+=f'<text x="{x}" y="{ly+i*21}" text-anchor="middle" font-size="18" font-weight="700" fill="#111">{html.escape(l)}</text>'
    return s
SH=(80,470); TT=(80,760); OP=(80,1000)
RX=1775
PD=(RX,805); ES=(RX,1040)
def hand(p,k=0.7): return (p[0]+42*k,p[1]+48*k)
def route(p,gx,ty,ex):
    h=hand(p); return f'<path d="M{h[0]},{h[1]} H{gx} V{ty} H{ex}" fill="none" stroke="#222" stroke-width="1.8"/>'
ln=[]
ln.append(route(SH,150,pos['blue'][1],pos['blue'][0]-172))
ln.append(route(SH,150,pos['orange'][1],pos['orange'][0]-172))
ln.append(route(SH,150,ey,AIx-200))
ln.append(f'<path d="M{hand(SH)[0]},{hand(SH)[1]} H150 V{ey+42} H{Wx-100} L{Wx-100+8},{ey+28}" fill="none" stroke="#222" stroke-width="1.8"/>')
ln.append(f'<path d="M{hand(TT)[0]},{hand(TT)[1]} H168 V{ey+52} H{Wx-40} L{Wx-40+2},{ey+29}" fill="none" stroke="#222" stroke-width="1.8"/>')
ln.append(route(TT,168,pos['green'][1]-12,pos['green'][0]-173))
ln.append(route(TT,168,pos['purple'][1]-12,pos['purple'][0]-173))
ln.append(route(OP,186,pos['green'][1]+14,pos['green'][0]-173))
ln.append(route(OP,186,pos['purple'][1]+14,pos['purple'][0]-173))
for key,(px,py) in (('green',PD),('purple',ES)):
    bx,by=pos[key]; band=band_by[key]; lane=band['y']+band['h']-5
    hnd=(px-30*0.7*1.0, py+48*0.7)
    ln.append(f'<path d="M{bx},{by+62} V{lane} H{px-60} V{hnd[1]} H{px-29}" fill="none" stroke="#222" stroke-width="1.8"/>')

for x in body: a(x)
for x in ln: a(x)
for x in over: a(x)
a(actor(*SH,'Shopper'))
a(actor(*TT,'Time Trigger','system'))
a(actor(*OP,'System\nOperator'))
a(actor(*PD,'Price Data\nProvider','external'))
a(actor(*ES,'Energy Signal\nProvider','external'))
a('</svg>')
open('../use-case.svg','w').write('\n'.join(o))
