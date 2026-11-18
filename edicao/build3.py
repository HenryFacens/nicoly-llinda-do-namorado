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

# ---------- 4. shot plan: one take per speaker turn ----------
shots = []
for v, t0, t1 in runs:
    shots.append([t0, t1, v if t1 - t0 >= 3.0 else 'W'])
forced = [(0, 3.5)] + [(t - 0.05, t + 2.6) for t, _, _ in qcards]
def apply_force(shots, a, b, kind='W'):
    res = []
    for s0, s1, k in shots:
        if s1 <= a or s0 >= b: res.append([s0, s1, k]); continue
        if s0 < a: res.append([s0, a, k])
        if s1 > b: res.append([b, s1, k])
    res.append([a, b, kind]); return sorted(res)
for a, b in forced: shots = apply_force(shots, max(0, a), b)
shots = merge(shots)
# absorb any shot shorter than 1.5s into its neighbour
ch = True
while ch:
    ch = False
    for j, s in enumerate(shots):
        if s[1] - s[0] < 1.5 and len(shots) > 1:
            if j > 0: shots[j - 1][1] = s[1]
            else: shots[1][0] = s[0]
            shots.pop(j); ch = True; break
    shots = merge(shots)
print('shots', len(shots), 'min', round(min(b - a for a, b, _ in shots), 2), 'qcards', len(qcards))
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

# ---------- 6. python compositor ----------
from PIL import Image, ImageDraw, ImageFilter, ImageFont
fB = lambda n: ImageFont.truetype(FONT_B, n); fR = lambda n: ImageFont.truetype(FONT_R, n)
shot_of = np.empty(int(TOUT * OFPS) + 2, dtype='<U1')
for a, b, k in shots: shot_of[int(round(a * OFPS)):int(round(b * OFPS)) + 1] = k
for i in range(len(shot_of)):
    if shot_of[i] == '': shot_of[i] = shot_of[i - 1] if i else 'W'
in_card = np.zeros(len(shot_of), bool); flash = np.zeros(len(shot_of))
for t, _, _ in qcards:
    f0 = int(round(t * OFPS)); in_card[max(0, f0 - 3):f0 + int(2.6 * OFPS)] = True
    for d in range(9): 
        if f0 + d < len(flash): flash[f0 + d] = 0.45 * (1 - d / 9)
lt_rng = {}
for p in 'LR':
    for a, b, k in shots:
        if k == p and b - a > 3: lt_rng[p] = (int((a + .3) * OFPS), int(min(b, a + 4) * OFPS)); break
def overlay_rgba(base, ov):
    a = ov[..., 3:4] / 255.0
    return (base * (1 - a) + ov[..., :3] * a).astype(np.uint8)
def text_layer(draw_fn):
    im = Image.new('RGBA', (1920, 1080), (0, 0, 0, 0)); draw_fn(ImageDraw.Draw(im)); return np.asarray(im).astype(np.float32)
def wide_text(d, title=True):
    if title:
        tw = d.textlength(TITLE, font=fB(40)); d.text(((1920 - tw) / 2, 60), TITLE, font=fB(40), fill=(255, 255, 255, 220))
    for x0, nm in ((80, NAMES['L'][0]), (960, NAMES['R'][0])):
        tw = d.textlength(nm, font=fR(32)); d.text((x0 + (880 - tw) / 2, 850), nm, font=fR(32), fill=(255, 255, 255, 255))
WT = text_layer(lambda d: wide_text(d, True)); WN = text_layer(lambda d: wide_text(d, False))
LT = {}
for p in 'LR':
    nm, role = NAMES[p]
    def dl(d, nm=nm, role=role):
        w = int(max(d.textlength(nm, font=fB(42)), d.textlength(role, font=fR(28)))) + 60
        d.rectangle([60, 60, 70, 180], fill=(242, 177, 52, 255)); d.rectangle([70, 60, 70 + w, 180], fill=(0, 0, 0, 150))
        d.text((98, 72), nm, font=fB(42), fill=(255, 255, 255, 255)); d.text((98, 132), role, font=fR(28), fill=(242, 177, 52, 255))
    LT[p] = text_layer(dl)
def compose(strip, k, fi):
    im = Image.frombuffer('RGB', (1920, 540), strip)
    if k in 'LR':
        x = 1 if k == 'L' else 963
        fr = np.asarray(im.crop((x, 1, x + 956, 539)).resize((1920, 1080), Image.BICUBIC))
        if k in lt_rng and lt_rng[k][0] <= fi < lt_rng[k][1]: fr = overlay_rgba(fr, LT[k])
    else:
        bg = im.resize((480, 135), Image.BILINEAR).filter(ImageFilter.GaussianBlur(6)).resize((1920, 1080), Image.BILINEAR)
        bg = np.asarray(bg).astype(np.float32) * 0.72
        fr = bg.astype(np.uint8)
        fr[330:837, 74:1846] = 230
        fr[336:831, 80:1840] = np.asarray(im.resize((1760, 495), Image.BICUBIC))
        fr = overlay_rgba(fr, WN if in_card[fi] else WT)
    if flash[fi] > 0: fr = (fr * (1 - flash[fi]) + 255 * flash[fi]).astype(np.uint8)
    return fr
# ---------- 7. frame pump + encode ----------
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
af = (f"highpass=f=80,afftdn=nf=-30,acompressor=threshold=-20dB:ratio=3:attack=10:release=150:makeup=2,"
      f"atempo={SPEED},loudnorm=I=-16:TP=-1.5:LRA=9,aresample=48000")
cmd = ['ffmpeg', '-v', 'error', '-stats', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '1920x1080', '-r', str(OFPS), '-i', '-',
       '-f', 's16le', '-ar', str(SR), '-ac', '1', '-i', 'cond.raw',
       '-vf', 'unsharp=5:5:0.5,subtitles=caps.ass:fontsdir=/usr/share/fonts/opentype/inter,format=yuv420p', '-af', af,
       '-t', f'{LIM:.3f}', '-c:v', 'libx264', '-preset', os.environ.get('PRESET', 'medium'),
       '-crf', '20', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', out]
enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
XF = 3; prev = None; prev_piece = None; blend_left = 0; blend_from = None
for f in range(int(LIM * OFPS)):
    tc = f / OFPS * SPEED
    j = min(max(0, bisect.bisect_right(C, tc) - 1), len(iv) - 1)
    k, st = src_at(tc)
    if k not in readers: readers[k] = Reader(k)
    fr = compose(readers[k].get(int(st * SFPS + 1e-6)), shot_of[f], f)
    # soften jump cuts (piece change within the same shot)
    if prev_piece is not None and j != prev_piece and f > 0 and shot_of[f] == shot_of[f - 1] and not flash[f]:
        blend_left = XF; blend_from = prev
    if blend_left:
        a = blend_left / (XF + 1)
        fr = (blend_from.astype(np.float32) * a + fr * (1 - a)).astype(np.uint8); blend_left -= 1
    enc.stdin.write(fr.tobytes()); prev = fr; prev_piece = j
enc.stdin.close(); enc.wait()
for r in readers.values(): r.p.kill()
