"""Render intro.mp4 and outro.mp4 (video only, 30fps, 1920x1080)."""
import subprocess, numpy as np, sys
from PIL import Image, ImageDraw, ImageFilter
from brand import *
OFPS = 30; SFPS = 16; B = 60 / 128
NAMES_L = 'Rita Cássia Camille Duarte Achilles'; NAMES_R = 'Nicoly Fayffer Duarte de Oliveira'

def strip_frames(k, t0, dur):
    n = int(np.ceil(dur * SFPS)) + 2
    p = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{t0:.3f}', '-i', f'in/{k}.mp4', '-frames:v', str(n),
                        '-vf', 'crop=1920:540:0:270', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
    return np.frombuffer(p, np.uint8).reshape(-1, 540, 1920, 3)

def layout(strip, kind):
    im = Image.fromarray(strip)
    if kind in 'LR':
        x = 1 if kind == 'L' else 963
        return np.asarray(im.crop((x, 1, x + 956, 539)).resize((1920, 1080), Image.BICUBIC))
    bg = im.resize((480, 135), Image.BILINEAR).filter(ImageFilter.GaussianBlur(6)).resize((1920, 1080), Image.BILINEAR)
    fr = (np.asarray(bg).astype(np.float32) * 0.6).astype(np.uint8)
    fr[290:797, 74:1846] = 230; fr[296:791, 80:1840] = np.asarray(im.resize((1760, 495), Image.BICUBIC))
    return fr

def zoom(fr, z):
    if z <= 1.001: return fr
    im = Image.fromarray(fr); w, h = int(1920 / z), int(1080 / z)
    return np.asarray(im.crop(((1920 - w) // 2, (1080 - h) // 2, (1920 + w) // 2, (1080 + h) // 2)).resize((1920, 1080), Image.BILINEAR))

def shade(fr, a): return (fr.astype(np.float32) * (1 - a)).astype(np.uint8)

def marquee(t, y, text='VIDA ÚTIL  •  PODCAST  •  ', size=230, speed=260, alpha=70):
    L = Image.new('RGBA', (1920, 1080), (0, 0, 0, 0)); d = ImageDraw.Draw(L); f = BLACK(size)
    w = d.textlength(text, font=f); x = -((t * speed) % w)
    while x < 1920:
        d.text((x, y), text, font=f, fill=(0, 0, 0, 0), stroke_width=3, stroke_fill=(255, 255, 255, alpha), anchor='lm'); x += w
    return np.asarray(L).astype(np.float32)

def pop(p):  # 0..1 -> scale with overshoot
    p = min(max(p, 0), 1); return 0.6 + 0.4 * (1 - (1 - p) ** 3) + 0.08 * np.sin(np.pi * p) * (p < 1)

def name_tag(label, name, sub, p):
    """slide-in lower-left tag; p in 0..1"""
    L = Image.new('RGBA', (1920, 1080), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
    off = (1 - ease(p)) * -900
    fl = BOLD(34); fn = BLACK(78); fs = MED(36)
    pw = d.textlength(label, font=fl) + 48
    x = 110 + off; y = 760
    d.rounded_rectangle([x, y, x + pw, y + 58], 29, fill=YEL); d.text((x + 24, y + 29), label, font=fl, fill=NAVY, anchor='lm')
    d.text((x, y + 80), name, font=fn, fill=WHITE, stroke_width=3, stroke_fill=(0, 0, 0, 160))
    if sub: d.text((x + 4, y + 182), sub, font=fs, fill=WHITE, stroke_width=2, stroke_fill=(0, 0, 0, 160))
    return np.asarray(L).astype(np.float32)

def center_text(lines, p, label=None):
    L = Image.new('RGBA', (1920, 1080), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
    a = int(255 * min(1, p * 2)); dy = (1 - ease(p)) * 40
    y = 380 + dy
    if label:
        fl = BOLD(38); pw = d.textlength(label, font=fl) + 56
        d.rounded_rectangle([960 - pw / 2, y, 960 + pw / 2, y + 64], 32, fill=YEL + (a,))
        d.text((960, y + 32), label, font=fl, fill=NAVY + (a,), anchor='mm'); y += 110
    for ln, sz in lines:
        f = BLACK(sz); d.text((960, y + sz / 2), ln, font=f, fill=(255, 255, 255, a), anchor='mm', stroke_width=4, stroke_fill=(0, 0, 0, int(a * .6)))
        y += sz * 1.12
    return np.asarray(L).astype(np.float32)

def paste_logo(fr, t, t0):
    p = (t - t0) / 0.35
    if p <= 0: return fr
    s = pop(p); tagp = (t - t0 - 0.35) / 0.3
    lg = logo(1.0 * s, tag_progress=max(0, tagp))
    im = Image.fromarray(fr); im.paste(lg, ((1920 - lg.width) // 2, (1080 - lg.height) // 2 - 20), lg)
    return np.asarray(im)

def render(out, frames_fn, nframes):
    enc = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '1920x1080', '-r', str(OFPS), '-i', '-',
                            '-c:v', 'libx264', '-preset', 'medium', '-crf', '17', '-pix_fmt', 'yuv420p', out], stdin=subprocess.PIPE)
    for f in range(nframes): enc.stdin.write(frames_fn(f).tobytes())
    enc.stdin.close(); enc.wait()

# ---------------- INTRO ----------------
SEGS = [  # (start beat, end beat, src key, src start, layout)
    (0, 6, 'ddca3e5e', 74.0, 'W'),
    (6, 9, '2fe938de', 18.4, 'L'),
    (9, 12, '2fe938de', 0.4, 'R'),
    (12, 15, '2fe938de', 38.4, 'W'),
]
cache = {}
for i, (b0, b1, k, s, lay) in enumerate(SEGS): cache[i] = strip_frames(k, s, (b1 - b0) * B)
NI = int(round(15 * B * OFPS))
def intro_frame(f):
    t = f / OFPS; b = t / B
    i = max(j for j, sg in enumerate(SEGS) if sg[0] <= b); b0, b1, k, s, lay = SEGS[i]
    tl = t - b0 * B; arr = cache[i]; fr = layout(arr[min(int(tl * SFPS), len(arr) - 1)], lay)
    # beat punch-zoom on each cut
    fr = zoom(fr, 1 + 0.07 * max(0, 1 - tl / 0.25))
    if i == 0:
        fr = shade(fr, 0.38); fr = over(fr, marquee(t, 540 + 330, alpha=60)); fr = over(fr, marquee(-t, 540 - 330, alpha=60))
        fr = paste_logo(fr, t, 0.12)
    elif i == 1:
        fr = over(shade(fr, 0.1), name_tag('CONVIDADA', 'Rita Achilles', 'Farmacêutica · Estabilidade pós-registro', (tl - .05) / .35))
    elif i == 2:
        fr = over(shade(fr, 0.1), name_tag('APRESENTAÇÃO', 'Nicoly Fayffer', 'Estudante de Farmácia · UNIP', (tl - .05) / .35))
    else:
        fr = shade(fr, 0.45); fr = over(fr, marquee(t, 540 + 380, alpha=55))
        fr = over(fr, center_text([('ESTABILIDADE PÓS-REGISTRO', 92), ('EM COMPRIMIDOS', 92)], (tl - .05) / .3, label='EP. 01'))
    # flash on the downbeat at the very start
    if t < 0.12: fr = (fr * (t / 0.12)).astype(np.uint8)
    # wipe in during the last half beat
    wt = 15 * B - 0.33
    if t >= wt: fr = wipe(fr, (t - wt) / 0.33, 'in')
    return fr

# ---------------- OUTRO ----------------
NO = int(round((8 * B + 1.6) * OFPS))
def outro_frame(f):
    t = f / OFPS; fr = panel_image().copy()
    # hide the static panel logo; draw animated content
    fr = np.full_like(fr, 0) + np.array(NAVY, np.uint8)
    d_im = Image.fromarray(fr); d = ImageDraw.Draw(d_im)
    for x in range(-1080, 1920, 70): d.line([x + int(t * 40) % 70, 1080, x + 1080 + int(t * 40) % 70, 0], fill=(17, 27, 48), width=24)
    fr = np.asarray(d_im)
    fr = over(fr, marquee(t, 960, alpha=35, size=180))
    p = (t - 0.35) / 0.35
    if p > 0:
        lg = logo(0.95 * pop(p), tag_progress=max(0, (t - 0.75) / 0.3)); im = Image.fromarray(fr)
        im.paste(lg, ((1920 - lg.width) // 2, 230), lg); fr = np.asarray(im)
    q = (t - 1.1) / 0.4
    if q > 0:
        L = Image.new('RGBA', (1920, 1080), (0, 0, 0, 0)); d = ImageDraw.Draw(L); a = int(255 * min(1, q))
        d.text((960, 640), 'Obrigado por assistir!', font=BLACK(70), fill=(255, 255, 255, a), anchor='mm')
        d.text((960, 735), f'Apresentação: {NAMES_R}', font=MED(34), fill=(200, 205, 215, a), anchor='mm')
        d.text((960, 785), f'Convidada: {NAMES_L}', font=MED(34), fill=(200, 205, 215, a), anchor='mm')
        # LinkedIn reminder
        x, y = 960 - 230, 860
        d.rounded_rectangle([x, y, x + 64, y + 64], 12, fill=(10, 102, 194, a))
        d.text((x + 32, y + 34), 'in', font=BOLD(42), fill=(255, 255, 255, a), anchor='mm')
        d.text((x + 86, y + 32), 'Rita Duarte no LinkedIn', font=BOLD(38), fill=(255, 255, 255, a), anchor='lm')
        fr = over(fr, np.asarray(L).astype(np.float32))
    # starts covered by the wipe panel, which slides away
    if t < 0.33: fr = wipe(fr, t / 0.33, 'out')
    if t > NO / OFPS - 0.5: fr = (fr * max(0, (NO / OFPS - t) / 0.5)).astype(np.uint8)
    return fr

if __name__ == '__main__':
    which = sys.argv[1:] or ['intro', 'outro']
    if 'intro' in which: render('intro.mp4', intro_frame, NI); print('intro', NI / OFPS)
    if 'outro' in which: render('outro.mp4', outro_frame, NO); print('outro', NO / OFPS)
