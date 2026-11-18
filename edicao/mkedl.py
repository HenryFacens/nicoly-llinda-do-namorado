import json,re
d=json.load(open('words.json'))
segs=[[s['k'],s['a'],s['b']] for s in d]
W=[]
for si,s in enumerate(d):
    for w in s['w']: W.append([si,w[0],w[1],w[2].strip(),True,''])
def R(a,b=None): return list(range(a,(b if b is not None else a)+1))
drop = (R(25,29)+R(56,60)+R(62,69)+[72]+R(76,94)+[96]+R(103,104)+R(111,122)
 +[179,184]+R(185,187)+[193,196,206]+R(249,252)+[274,311,335,350]+R(354,358)+R(377,389)+[391,401,407,428,429]
 +[486,492,518,595,622,623,629,647,648,656,660]+R(663,667)+R(678,684)+R(697,717)+[726,730]+R(732,735)+[746,757,802]+R(810,818)+[828,829,836]
 +[867,871,872,874,875,881,882]+R(884,889)+[898,906,918,948,949,973,989,1006]+R(1007,1013)+[1028,1046,1073,1091,1094,1105]
 +[1106,1117,1118,1169]+R(1170,1189)+[1247,1280,1334,1335,1357]
 +[1448]+R(1415,1427)+R(1453,1461)+[1489]+R(1503,1505))
for i in drop: W[i][4]=False
for w in W:  # safety: any leftover né
    if re.sub(r'[^\wé]','',w[3].lower())=='né': w[4]=False
fix={43:'USF',24:'Achilles',139:'degradação',161:'Farmacopeia',360:'POPs',367:'rastreabilidade,',373:'rastreabilidade',494:'gratificantes',
     1293:'móvel,',1316:'dissolutor,',1318:'Karl Fischer,',1320:'UPLC,',1358:'à',1494:'LinkedIn',787:'análises',
     685:'O',690:'foi',97:'começar',95:'Vamos',876:'Para',1107:'Você',1189:'',390:'Se',1129:'se'}
for i,t in fix.items(): W[i][3]=t
for i,w in enumerate(W):  # merge hyphen tokens into previous word for captions
    if w[3].startswith('-') and i>0:
        W[i-1][3]=W[i-1][3]+w[3]; w[3]=''
    if w[3].lower()=='fisico'+'' : w[3]='físico'
for i,w in enumerate(W):
    if w[3].lower().startswith('fisico'): w[3]='físico'+w[3][6:]
Q={105:'1:Quando os testes contam histórias diferentes',436:'2:Monitorar o medicamento no mercado',
   624:'3:O que encanta na estabilidade',876:'4:O que faz os recrutadores se encantarem',1107:'5:Quais instrumentos estudar'}
for i,t in Q.items(): W[i][5]='q:'+t; assert W[i][4]
for i in [125,128,373,521,838,938,940,994,1027,1037,1218,1352,1381,1400,1401]: W[i][5]='emph'; assert W[i][4],i
W[1491][5]='li'
json.dump({'segs':segs,'words':W},open('edl.json','w'),ensure_ascii=False)
kept=[w for w in W if w[4]]
print(len(W),len(kept))
print(' '.join(w[3] for w in kept))
