import json,numpy as np
from faster_whisper import WhisperModel
SEGS=[('2fe938de',0,99.5),('a0428eae',0.2,158.3),('61e504df',2.4,14.4),('61e504df',25.6,218.3),('80c6c5b3',60.35,200.3),('bbfd9658',32.5,43.9),('bbfd9658',49.55,161.4),('f214de29',83.2,119.6),('ddca3e5e',26.6,79.2)]
m=WhisperModel('large-v3-turbo',device='cpu',compute_type='int8',cpu_threads=4)
P="Então, é... né? Tipo, ahn, hum, é, assim, aí. A gente, né, tá. HPLC, Anvisa, farmacopeia, pós-registro, estabilidade, comprimidos."
out=[]
for k,a,b in SEGS:
    raw=np.frombuffer(open(f'{k}.wav','rb').read()[44:],np.int16).astype(np.float32)/32768
    x=raw[int(a*16000):int(b*16000)]
    segs,_=m.transcribe(x,language='pt',word_timestamps=True,initial_prompt=P,condition_on_previous_text=False)
    ws=[(round(w.start+a,3),round(w.end+a,3),w.word,round(w.probability,2)) for s in segs for w in s.words]
    out.append({'k':k,'a':a,'b':b,'w':ws}); print(k,a,len(ws),flush=True)
json.dump(out,open('words.json','w'),ensure_ascii=False)
