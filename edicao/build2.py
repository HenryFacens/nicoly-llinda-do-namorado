"""Word-level podcast edit.  python3 build2.py edl.json out.mp4
edl.json: {"words": [[seg, src_start, src_end, text, keep(bool), tag]], ...}
  tag: "" | "emph" (keyword pop + punch-in) | "q:<n>:<title>" (question card + flash, on first word of a question)
"""
import json, subprocess, sys, os, bisect, numpy as np, re

SPEED = float(os.environ.get('SPEED', 1.2)); OFPS = 30; SFPS = 16; SR = 48000
FONT_B = '/usr/share/fonts/opentype/inter/Inter-Bold.otf'
FONT_R = '/usr/share/fonts/opentype/inter/Inter-Medium.otf'
NAMES = {'L': ('Rita Achiles', 'Farmacêutica · Estabilidade pós-registro'),
         'R': ('Nicoly Fayffer Duarte de Oliveira', 'Apresentação')}
TITLE = 'ESTABILIDADE PÓS-REGISTRO EM COMPRIMIDOS'
edl = json.load(open(sys.argv[1])); out = sys.argv[2]
segs = edl['segs']  # [[k,a,b]]
W = edl['words']

# ---------- 1. kept source intervals from kept words ----------
GAPMAX, GAPKEEP, PRE, POST = 0.18, 0.07, 0.05, 0.07
iv = []  # [k, a, b, [word indices]]
prev = None
for i, (s, t0, t1, txt, keep, tag) in enumerate(W):
    if not keep: prev = None; continue
    k = segs[s][0]
    # bounds: don't eat into neighbouring words more than halfway
    lo = W[i - 1][2] if i > 0 and W[i - 1][0] == s else segs[s][1]
    hi = W[i + 1][1] if i + 1 < len(W) and W[i + 1][0] == s else segs[s][2]
    a = max(t0 - PRE, (lo + t0) / 2, segs[s][1]); b = min(t1 + POST, (t1 + hi) / 2, segs[s][2])
    if prev is not None and iv and iv[-1][0] == k and W[prev][0] == s and prev == i - 1:
        gap = t0 - W[prev][2]
        if gap <= GAPMAX: iv[-1][2] = b; iv[-1][3].append(i); prev = i; continue
        # long pause between consecutive words: keep a short breath
        mid = W[prev][2] + POST + GAPKEEP
        iv[-1][2] = min(mid, t0 - PRE)
        iv.append([k, t0 - PRE, b, [i]]); prev = i; continue
    iv.append([k, a, b, [i]]); prev = i
iv = [x for x in iv if x[2] - x[1] > 0.06]

# ---------- 2. audio (sample exact, 6ms fades) ----------
srcw = {}
def wav(k):
    if k not in srcw:
        p = subprocess.run(['ffmpeg', '-v', 'error', '-i', f'in/{k}.mp4', '-ac', '1', '-ar', str(SR), '-f', 's16le', '-'],
                           capture_output=True).stdout
        srcw[k] = np.frombuffer(p, np.int16).astype(np.float32)
    return srcw[k]
F = int(0.006 * SR); ramp = np.linspace(0, 1, F)
chunks, C = [], [0.0]  # C: condensed start time of each interval
for k, a, b, _ in iv:
    x = wav(k)[int(round(a * SR)):int(round(b * SR))].copy()
    if len(x) > 2 * F: x[:F] *= ramp; x[-F:] *= ramp[::-1]
    chunks.append(x); C.append(C[-1] + len(x) / SR)
aud = np.concatenate(chunks).clip(-32768, 32767).astype(np.int16)
open('cond.raw', 'wb').write(aud.tobytes())
TC = C[-1]; TOUT = TC / SPEED
print(f'intervals={len(iv)} condensed={TC:.1f}s final={TOUT:.1f}s')

def c2o(tc): return tc / SPEED
# word -> condensed time
wpos = {}
for j, (k, a, b, idx) in enumerate(iv):
    for i in idx:
        wpos[i] = (C[j] + max(0, W[i][1] - a), C[j] + min(b - a, W[i][2] - a))

# ---------- 3. speaker per output time ----------
def speaker(k):
    p = subprocess.run(['ffmpeg', '-v', 'error', '-i', f'in/{k}.mp4', '-vf', 'fps=4,crop=1920:26:0:1060,scale=480:26',
                        '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
    a = np.frombuffer(p, np.uint8).reshape(-1, 26, 480, 3).astype(int)
    pur = lambda r: ((r[..., 2] - r[..., 0] > 40) & (r[..., 2] > 120)).mean(axis=(1, 2))
    L, R = pur(a[:, :, 0:60]), pur(a[:, :, 240:310])
    return ['L' if l > .2 and l > r else 'R' if r > .2 else None for l, r in zip(L, R)]
spk = {}
def src_at(tc):
    j = max(0, bisect.bisect_right(C, tc) - 1); j = min(j, len(iv) - 1)
    k, a, b, _ = iv[j]; return k, min(b, a + tc - C[j])
NF = int(TOUT * OFPS)
lab, last = [], 'R'
for f in range(0, NF, 4):  # sample every 4 output frames
    k, st = src_at(f / OFPS * SPEED)
    if k not in spk: spk[k] = speaker(k)
    v = spk[k][min(int((st + 0.35) * 4), len(spk[k]) - 1)] or last; last = v; lab.append(v)
dt = 4 / OFPS
runs = []
for i, v in enumerate(lab):
    if runs and runs[-1][0] == v: runs[-1][2] = (i + 1) * dt
    else: runs.append([v, i * dt, (i + 1) * dt])
def merge(rs):
    m = []
    for r in rs:
        if m and m[-1][0] == r[0]: m[-1][2] = r[2]
        else: m.append(list(r))
    return m
ch = True
while ch:
    ch = False
    for j, r in enumerate(runs):
        if r[2] - r[1] < 1.2 and len(runs) > 1:
            if j > 0: runs[j - 1][2] = r[2]
            else: runs[1][1] = r[1]
            runs.pop(j); ch = True; break
    runs = merge(runs)

# key moments (output time)
qcards, emph = [], []
for i, w in enumerate(W):
    if i not in wpos: continue
    t = c2o(wpos[i][0])
    if w[5].startswith('q:'): _, n, title = w[5].split(':', 2); qcards.append((t, n, title))
    elif w[5] == 'emph': emph.append((t, c2o(wpos[i][1])))

# ---------- 4. shot plan ----------
shots = []
for v, t0, t1 in runs:
    o = 'R' if v == 'L' else 'L'; n = 0
    while t1 - t0 > 0.01:
        L = 4.0 if n % 2 == 0 else 5.0
        if t1 - t0 < L + 2: L = t1 - t0
        kind = [v, v + 'T', v, 'W', v + 'T', o][n % 6] if n else v
        if kind == o: L = min(L, 1.6)
        if kind == 'W': L = min(L, 2.5)
        shots.append([t0, t0 + L, kind]); t0 += L; n += 1
# force wide on opening & question cards
forced = [(0, 3.5)] + [(t - 0.05, t + 2.6) for t, _, _ in qcards]
def apply_force(shots, a, b, kind='W'):
    res = []
    for s0, s1, k in shots:
        if s1 <= a or s0 >= b: res.append([s0, s1, k]); continue
        if s0 < a: res.append([s0, a, k])
        if s1 > b: res.append([b, s1, k])
    res.append([a, b, kind]); return sorted(res)
for a, b in forced: shots = apply_force(shots, max(0, a), b)
shots = [s for s in merge(shots) if s[1] - s[0] > 0.05]
print('shots', len(shots), 'qcards', len(qcards), 'emph', len(emph))

def anyb(kinds, sh=None):
    rs = [f'between(t,{a:.3f},{b - 0.001:.3f})' for a, b, k in (sh or shots) if k in kinds]
    return '+'.join(rs) if rs else '0'

# ---------- 5. ASS captions ----------
def ts(t):
    t = max(0, t); h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f'{h}:{m:02d}:{s:05.2f}'
def clean(x): return x.strip().replace('{', '').replace('}', '')
ass = ['[Script Info]', 'ScriptType: v4.00+', 'PlayResX: 1920', 'PlayResY: 1080', 'WrapStyle: 0', '',
       '[V4+ Styles]',
       'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
       'Style: Cap,Inter,68,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,5,2,2,120,120,70,1',
       'Style: Card,Inter,40,&H0034B1F2,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,6,0,1,0,0,5,80,80,0,1',
       'Style: CardT,Inter,88,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,4,3,5,160,160,0,1', '',
       '[Events]', 'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
YEL = '&H0034B1F2&'
kw = [(i, W[i], wpos[i]) for i in range(len(W)) if i in wpos and clean(W[i][3])]
# group into caption chunks: max 4 words / 22 chars, break at punctuation or pauses
chunks, cur = [], []
for n, (i, w, (a, b)) in enumerate(kw):
    if cur and (len(cur) >= 4 or sum(len(clean(x[1][3])) + 1 for x in cur) + len(clean(w[3])) > 24
                or a - cur[-1][2][1] > 0.35 or w[5].startswith('q:') or re.search(r'[.?!]$', clean(cur[-1][1][3]))):
        chunks.append(cur); cur = []
    cur.append((i, w, (a, b)))
    if re.search(r'[.?!,]$', clean(w[3])) and len(cur) >= 2: chunks.append(cur); cur = []
if cur: chunks.append(cur)
qt = [t for t, _, _ in qcards]
for ci, c in enumerate(chunks):
    st = c2o(c[0][2][0]); en = c2o(c[-1][2][1]) + 0.15
    if ci + 1 < len(chunks): en = min(en, c2o(chunks[ci + 1][0][2][0]))
    words = [clean(x[1][3]).upper().rstrip(',') for x in c]
    for j, x in enumerate(c):
        ws = c2o(x[2][0]) if j else st
        we = c2o(c[j + 1][2][0]) if j + 1 < len(c) else en
        if we - ws < 0.02: continue
        parts = []
        for m, wd in enumerate(words):
            e = c[m][1][5] == 'emph'
            if m == j:
                pop = r'{\t(0,90,\fscx118\fscy118)\t(90,180,\fscx100\fscy100)}' if e else ''
                parts.append(f'{{\\c{YEL}}}{pop}{wd}{{\\r}}')
            elif e: parts.append(f'{{\\c{YEL}}}{wd}{{\\r}}')
            else: parts.append(wd)
        inq = any(q - 0.1 <= ws < q + 2.6 for q in qt)
        pos = r'{\an2\pos(960,1010)}' if not inq else r'{\an2\pos(960,1010)\alpha&H30&}'
        ass.append(f'Dialogue: 1,{ts(ws)},{ts(we)},Cap,,0,0,0,,{pos}{" ".join(parts)}')
for t, n, title in qcards:
    fx = r'{\fad(150,250)\fscx75\fscy75\t(0,220,\fscx100\fscy100)}'
    ass.append(f'Dialogue: 2,{ts(t)},{ts(t + 2.5)},Card,,0,0,0,,{{\\pos(960,170)}}{{\\fad(150,250)}}PERGUNTA {n}')
    ass.append(f'Dialogue: 2,{ts(t)},{ts(t + 2.5)},CardT,,0,0,0,,{{\\pos(960,250)}}{fx}{title.upper()}')
open('caps.ass', 'w').write('\n'.join(ass) + '\n')

# ---------- 6. filter graph ----------
def esc(s): return s.replace(':', r'\:').replace("'", r"\'")
lt = {'L': [], 'R': []}
for a, b, k in shots:
    p = k[0]
    if k != 'W' and len(lt[p]) < 1 and b - a > 2: lt[p].append((a + 0.3, min(b, a + 3.8)))
isR = anyb({'R', 'RT'})
# punch-in: snap zoom 1.12 on emphasized words (hold 0.9s), skip during wide shots
zexp = '+'.join(f'between(t,{a:.3f},{a + 0.9:.3f})' for a, _ in emph) or '0'
flash = '+'.join(f'between(t,{t:.3f},{t + 0.3:.3f})*(1-(t-{t:.3f})/0.3)' for t, _, _ in qcards) or '0'
fc = ['[0:v]split=4[s1][s2][s3][s4]',
      f"[s1]crop=w=956:h=538:x='if({isR},963,1)':y=1,scale=1920:1080:flags=lanczos,unsharp=5:5:0.6[cu]",
      f"[s2]crop=w=800:h=450:x='if({isR},963+78,1+78)':y=70,scale=1920:1080:flags=lanczos,unsharp=5:5:0.7[ct]",
      '[s3]scale=480:135,boxblur=12:2,scale=1920:1080,eq=brightness=-0.2:saturation=0.8[bg]',
      '[s4]scale=1760:495:flags=lanczos,pad=1772:507:6:6:color=white@0.9[fr]',
      f"[bg][fr]overlay=74:330,drawtext=fontfile={FONT_B}:text='{esc(TITLE)}':fontsize=40:fontcolor=white@0.85:x=(w-tw)/2:y=60:enable='not({anyb({'W'}, [[q - .1, q + 2.6, 'W'] for q in qt])})',"
      f"drawtext=fontfile={FONT_R}:text='{esc(NAMES['L'][0])}':fontsize=32:fontcolor=white:x=80+(880-tw)/2:y=850,"
      f"drawtext=fontfile={FONT_R}:text='{esc(NAMES['R'][0])}':fontsize=32:fontcolor=white:x=960+(880-tw)/2:y=850[wide]",
      f"[wide][cu]overlay=0:0:enable='{anyb({'L', 'R'})}'[x1]",
      f"[x1][ct]overlay=0:0:enable='{anyb({'LT', 'RT'})}'[x2]"]
dtx = []
for p, ivs in lt.items():
    en = '+'.join(f'between(t,{a:.3f},{b:.3f})' for a, b in ivs) or '0'
    nm, role = NAMES[p]
    dtx += [f"drawbox=x=60:y=60:w=10:h=120:color=0xF2B134:t=fill:enable='{en}'",
            f"drawbox=x=70:y=60:w={max(len(nm) * 25, len(role) * 16) + 60}:h=120:color=black@0.6:t=fill:enable='{en}'",
            f"drawtext=fontfile={FONT_B}:text='{esc(nm)}':fontsize=42:fontcolor=white:x=98:y=78:enable='{en}'",
            f"drawtext=fontfile={FONT_R}:text='{esc(role)}':fontsize=28:fontcolor=0xF2B134:x=98:y=134:enable='{en}'"]
wide_now = anyb({'W'})
fc.append(f"[x2]scale=w='1920*(1+0.12*gt({zexp},0)*not({wide_now}))':h='1080*(1+0.12*gt({zexp},0)*not({wide_now}))':eval=frame,"
          f"crop=1920:1080,eq=brightness='0.55*({flash})':eval=frame,{','.join(dtx)},subtitles=caps.ass:fontsdir=/usr/share/fonts/opentype/inter,format=yuv420p[vout]")
fc.append(f"[1:a]highpass=f=80,afftdn=nf=-30,acompressor=threshold=-20dB:ratio=3:attack=10:release=150:makeup=2,"
          f"atempo={SPEED},loudnorm=I=-16:TP=-1.5:LRA=9,aresample=48000[aout]")
open('fc2.txt', 'w').write(';\n'.join(fc))

# ---------- 7. frame pump ----------
class Reader:
    def __init__(s, k):
        s.p = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', f'in/{k}.mp4', '-vf', 'crop=1920:540:0:270',
                                '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE, bufsize=10 ** 8)
        s.n = -1; s.buf = None
    def get(s, idx):
        while s.n < idx:
            b = s.p.stdout.read(1920 * 540 * 3)
            if len(b) < 1920 * 540 * 3: break
            s.buf = b; s.n += 1
        return s.buf
readers = {}
LIM = float(os.environ.get('PREVIEW', 0)) or TOUT
cmd = ['ffmpeg', '-v', 'error', '-stats', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '1920x540', '-r', str(OFPS), '-i', '-',
       '-f', 's16le', '-ar', str(SR), '-ac', '1', '-i', 'cond.raw', '-filter_complex_script', 'fc2.txt',
       '-map', '[vout]', '-map', '[aout]', '-t', f'{LIM:.3f}', '-c:v', 'libx264', '-preset', os.environ.get('PRESET', 'medium'),
       '-crf', '20', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', out]
enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
for f in range(int(LIM * OFPS)):
    k, st = src_at(f / OFPS * SPEED)
    if k not in readers: readers[k] = Reader(k)
    enc.stdin.write(readers[k].get(int(st * SFPS + 1e-6)))
enc.stdin.close(); enc.wait()
for r in readers.values(): r.p.kill()
