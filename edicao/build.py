"""Podcast-style edit: python3 build.py <out.mp4> <file:a-b> [<file:a-b> ...]
file = key in in/, a-b = source seconds kept (before silence trimming)."""
import subprocess, sys, re, os, numpy as np
FPS = 16; SPEED = 1.12; TFPS = 4  # speaker sampling fps
FONT_B = '/usr/share/fonts/opentype/inter/Inter-Bold.otf'
FONT_R = '/usr/share/fonts/opentype/inter/Inter-Medium.otf'
NAMES = {'L': ('Rita Achiles', 'Farmacêutica · Estabilidade pós-registro'),
         'R': ('Nicoly Fayffer Duarte de Oliveira', 'Apresentação')}
TITLE = 'ESTABILIDADE PÓS-REGISTRO EM COMPRIMIDOS'

out = sys.argv[1]
segs = []
for s in sys.argv[2:]:
    k, r = s.split(':'); a, b = map(float, r.split('-')); segs.append((k, a, b))

def silences(k):
    e = subprocess.run(['ffmpeg', '-i', f'in/{k}.mp4', '-af', 'highpass=f=100,silencedetect=noise=-36dB:d=0.32',
                        '-f', 'null', '-'], capture_output=True, text=True).stderr
    st = [float(x) for x in re.findall(r'silence_start: ([\d.]+)', e)]
    en = [float(x) for x in re.findall(r'silence_end: ([\d.]+)', e)]
    return list(zip(st, en + [1e9] * (len(st) - len(en))))

def speaker(k):
    W, H = 480, 26
    p = subprocess.run(['ffmpeg', '-v', 'error', '-i', f'in/{k}.mp4', '-vf',
                        f'fps={TFPS},crop=1920:26:0:1060,scale={W}:{H}', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                       capture_output=True).stdout
    a = np.frombuffer(p, np.uint8).reshape(-1, H, W, 3).astype(int)
    pur = lambda r: ((r[..., 2] - r[..., 0] > 40) & (r[..., 2] > 120)).mean(axis=(1, 2))
    L, R = pur(a[:, :, 0:60]), pur(a[:, :, 240:310])
    return ['L' if l > .2 and l > r else 'R' if r > .2 else None for l, r in zip(L, R)]

# 1. kept intervals (frame-snapped), condensed timeline
PAD, MINGAP = 0.12, 0.22
pieces = []  # (k, f0, f1)
for k, a, b in segs:
    keep = [[a, b]]
    for s0, s1 in silences(k):
        s0, s1 = s0 + PAD, s1 - PAD
        if s1 - s0 < MINGAP: continue
        nk = []
        for x0, x1 in keep:
            if s1 <= x0 or s0 >= x1: nk.append([x0, x1]); continue
            if s0 > x0: nk.append([x0, s0])
            if s1 < x1: nk.append([s1, x1])
        keep = nk
    for x0, x1 in keep:
        f0, f1 = round(x0 * FPS), round(x1 * FPS)
        if f1 - f0 >= 4: pieces.append((k, f0, f1))
src_total = sum(b - a for _, a, b in segs); cond_total = sum(f1 - f0 for _, f0, f1 in pieces) / FPS
print(f'pieces={len(pieces)} source={src_total:.1f}s condensed={cond_total:.1f}s final={cond_total/SPEED:.1f}s')

# 2. speaker on condensed timeline (sampled per output frame)
spk_cache = {}
cs = []
for k, f0, f1 in pieces:
    if k not in spk_cache: spk_cache[k] = speaker(k)
    sp = spk_cache[k]
    for f in range(f0, f1):
        i = int((f / FPS + 0.35) * TFPS)  # highlight lags audio a bit
        cs.append(sp[min(i, len(sp) - 1)])
last = 'R'
for i, v in enumerate(cs):
    if v is None: cs[i] = last
    last = cs[i]
# runs, merge short ones (<1.3s)
runs = []
for i, v in enumerate(cs):
    if runs and runs[-1][0] == v: runs[-1][2] = i + 1
    else: runs.append([v, i, i + 1])
changed = True
while changed:
    changed = False
    for j, (v, s, e) in enumerate(runs):
        if e - s < 1.3 * FPS and len(runs) > 1:
            if j > 0: runs[j - 1][2] = e
            else: runs[1][1] = s
            runs.pop(j); changed = True; break
    m = []
    for r in runs:
        if m and m[-1][0] == r[0]: m[-1][2] = r[2]
        else: m.append(r)
    runs = m

# 3. shot plan: (start_s, end_s, kind) kind in L,R,LT,RT,W
shots = []
first = True
for v, s, e in runs:
    t0, t1 = s / FPS, e / FPS
    other = 'R' if v == 'L' else 'L'
    if first:  # open on wide
        w = min(4.0, t1 - t0); shots.append((t0, t0 + w, 'W')); t0 += w; first = False
    seq, n = [], 0
    while t1 - t0 > 0.01:
        rem = t1 - t0
        L = 4.5 if n % 2 == 0 else 5.5
        if rem < L + 2.5: L = rem
        kind = [v, v + 'T', v, 'W', v + 'T', other][n % 6] if n else v
        if kind == other: L = min(L, 1.8)
        if kind == 'W': L = min(L, 3.0)
        shots.append((t0, t0 + L, kind)); t0 += L; n += 1
# merge adjacent identical
m = []
for sh in shots:
    if m and m[-1][2] == sh[2]: m[-1] = (m[-1][0], sh[1], sh[2])
    else: m.append(sh)
shots = m
print('shots', len(shots))

def anyb(kinds):
    rs = [f'between(t,{a:.4f},{b - 0.001:.4f})' for a, b, k in shots if k in kinds]
    return '+'.join(rs) if rs else '0'

# lower thirds: first 2 close-ups per person, 3.5s
lt = {'L': [], 'R': []}
for a, b, k in shots:
    p = k[0]
    if k != 'W' and len(lt[p]) < 2 and b - a > 2: lt[p].append((a + 0.3, min(b, a + 3.8)))

def esc(s): return s.replace(':', r'\:').replace("'", r"\'")

# 4. filter graph
ins, fc = [], []
keys = []
for k, _, _ in segs:
    if k not in keys: keys.append(k)
for k in keys: ins += ['-i', f'in/{k}.mp4']
cat = []
for i, k in enumerate(keys):
    pk = [(f0, f1) for kk, f0, f1 in pieces if kk == k]
    vsel = '+'.join(f'between(n,{f0},{f1 - 1})' for f0, f1 in pk)
    asel = '+'.join(f'between(t,{f0 / FPS:.4f},{f1 / FPS - 1e-5:.5f})' for f0, f1 in pk)
    fc.append(f"[{i}:v]select='{vsel}',setpts=N/{FPS}/TB,crop=1920:540:0:270[v{i}]")
    fc.append(f"[{i}:a]aresample=48000,aselect='{asel}',asetpts=N/SR/TB[a{i}]")
    cat.append(f'[v{i}][a{i}]')
# NB: keys are processed in segs order; segs must list each file contiguously
fc.append(f"{''.join(cat)}concat=n={len(keys)}:v=1:a=1[strip][araw]")
fc.append('[strip]split=4[s1][s2][s3][s4]')
isR = anyb({'R', 'RT'})
fc.append(f"[s1]crop=w=956:h=538:x='if({isR},963,1)':y=1,scale=1920:1080:flags=lanczos,unsharp=5:5:0.6[cu]")
fc.append(f"[s2]crop=w=800:h=450:x='if({isR},963+78,1+78)':y=70,scale=1920:1080:flags=lanczos,unsharp=5:5:0.7[ct]")
# wide: blurred bg + framed strip + title
fc.append('[s3]scale=480:135,boxblur=12:2,scale=1920:1080,eq=brightness=-0.18:saturation=0.8[bg]')
fc.append('[s4]scale=1760:495:flags=lanczos,pad=1772:507:6:6:color=white@0.9[fr]')
fc.append(f"[bg][fr]overlay=74:330,drawtext=fontfile={FONT_B}:text='{esc(TITLE)}':fontsize=46:fontcolor=white:x=(w-tw)/2:y=200,"
          f"drawbox=x=(1920-160)/2:y=268:w=160:h=5:color=0xF2B134:t=fill,"
          f"drawtext=fontfile={FONT_R}:text='{esc(NAMES['L'][0])}':fontsize=34:fontcolor=white:x=80+(880-tw)/2:y=870,"
          f"drawtext=fontfile={FONT_R}:text='{esc(NAMES['R'][0])}':fontsize=34:fontcolor=white:x=960+(880-tw)/2:y=870[wide]")
fc.append(f"[wide][cu]overlay=0:0:enable='{anyb({'L', 'R'})}'[x1]")
fc.append(f"[x1][ct]overlay=0:0:enable='{anyb({'LT', 'RT'})}'[x2]")
dt = []
for p, ivs in lt.items():
    en = '+'.join(f'between(t,{a:.3f},{b:.3f})' for a, b in ivs) or '0'
    nm, role = NAMES[p]
    dt.append(f"drawbox=x=70:y=860:w=12:h=130:color=0xF2B134:t=fill:enable='{en}'")
    dt.append(f"drawbox=x=82:y=860:w={max(len(nm) * 26, len(role) * 17) + 70}:h=130:color=black@0.62:t=fill:enable='{en}'")
    dt.append(f"drawtext=fontfile={FONT_B}:text='{esc(nm)}':fontsize=44:fontcolor=white:x=112:y=882:enable='{en}'")
    dt.append(f"drawtext=fontfile={FONT_R}:text='{esc(role)}':fontsize=30:fontcolor=0xF2B134:x=112:y=942:enable='{en}'")
fc.append(f"[x2]{','.join(dt)},setpts=PTS/{SPEED},fps=30,format=yuv420p[vout]")
fc.append(f"[araw]highpass=f=80,afftdn=nf=-30,acompressor=threshold=-20dB:ratio=3:attack=10:release=150:makeup=2,"
          f"atempo={SPEED},loudnorm=I=-16:TP=-1.5:LRA=9,aresample=48000[aout]")
open('fc.txt', 'w').write(';\n'.join(fc))
cmd = ['ffmpeg', '-v', 'error', '-stats', '-y', *ins, '-filter_complex_script', 'fc.txt', '-map', '[vout]', '-map', '[aout]',
       '-c:v', 'libx264', '-preset', os.environ.get('PRESET', 'medium'), '-crf', '20', '-c:a', 'aac', '-b:a', '192k',
       '-movflags', '+faststart', out]
if os.environ.get('PREVIEW'): cmd[cmd.index(out):cmd.index(out)] = ['-t', os.environ['PREVIEW']]
subprocess.run(cmd, check=True)
