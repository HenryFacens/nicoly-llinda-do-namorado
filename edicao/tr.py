import sys,json,numpy as np
from faster_whisper import WhisperModel
m=WhisperModel('small',device='cpu',compute_type='int8',cpu_threads=4)
for k in sys.argv[1:]:
    segs,_=m.transcribe(np.frombuffer(open(f'{k}.wav','rb').read()[44:],np.int16).astype(np.float32)/32768,language='pt',word_timestamps=True,vad_filter=False)
    out=[]
    for s in segs:
        out.append({'s':s.start,'e':s.end,'t':s.text,'w':[(w.start,w.end,w.word) for w in s.words]})
    json.dump(out,open(f'{k}.json','w'),ensure_ascii=False)
    print(k,'done',flush=True)
