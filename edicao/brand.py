"""Brand kit for 'Vida Útil' podcast: logo, wipe transition, corner bug."""
import numpy as np
from PIL import Image, ImageDraw, ImageFont
FD = '/usr/share/fonts/opentype/inter/'
def F(name, n): return ImageFont.truetype(FD + name, n)
BLACK = lambda n: F('InterDisplay-Black.otf', n)
BOLD = lambda n: F('Inter-Bold.otf', n)
MED = lambda n: F('Inter-Medium.otf', n)
NAVY = (13, 21, 38); YEL = (242, 177, 52); WHITE = (255, 255, 255)
NAME = 'VIDA ÚTIL'

def mic_icon(d, x, y, s, col=WHITE):
    """pill-shaped microphone (capsule half yellow / half white) with stand. (x,y)=top-left, s=scale"""
    w, h = 64 * s, 118 * s
    d.rounded_rectangle([x, y, x + w, y + h], radius=w / 2, fill=col)
    d.rounded_rectangle([x, y, x + w, y + h * 0.5 + w / 2], radius=w / 2, fill=YEL)
    d.rectangle([x, y + h * 0.5 - 2 * s, x + w, y + h * 0.5 + 2 * s], fill=NAVY)
    lw = max(2, int(9 * s))
    d.arc([x - 22 * s, y + h * 0.35, x + w + 22 * s, y + h + 22 * s], 0, 180, fill=col, width=lw)
    d.line([x + w / 2, y + h + 22 * s, x + w / 2, y + h + 50 * s], fill=col, width=lw)
    d.line([x + w / 2 - 28 * s, y + h + 50 * s, x + w / 2 + 28 * s, y + h + 50 * s], fill=col, width=lw)
    return 64 * s + 22 * s, 118 * s + 50 * s  # approx extents

def logo(scale=1.0, tag='PODCAST · FARMÁCIA UNIP', tag_progress=1.0):
    """returns RGBA PIL image of the full logo (icon + wordmark + tag pill)"""
    s = scale; im = Image.new('RGBA', (int(1300 * s), int(330 * s)), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    f = BLACK(int(150 * s))
    tw = d.textlength(NAME, font=f)
    icon_w = 110 * s; gap = 34 * s
    total = icon_w + gap + tw; x0 = (im.width - total) / 2
    mic_icon(d, x0 + 12 * s, 20 * s, 1.15 * s)
    d.text((x0 + icon_w + gap, 120 * s), NAME, font=f, fill=WHITE, anchor='lm', stroke_width=int(3 * s), stroke_fill=(0, 0, 0, 90))
    if tag and tag_progress > 0:
        ft = BOLD(int(34 * s)); pw = d.textlength(tag, font=ft) + 50 * s; ph = 56 * s
        px = x0 + icon_w + gap + 6 * s; py = 205 * s
        vis = pw * min(1, tag_progress)
        d.rounded_rectangle([px, py, px + vis, py + ph], radius=ph / 2, fill=YEL)
        if tag_progress >= 0.6:
            d.text((px + 25 * s, py + ph / 2), tag, font=ft, fill=NAVY, anchor='lm')
    return im

_logo_full = None
def panel_image():
    """full-frame navy panel with centered logo, used under wipes"""
    global _logo_full
    if _logo_full is None:
        im = Image.new('RGB', (1920, 1080), NAVY)
        # subtle diagonal stripes
        d = ImageDraw.Draw(im)
        for x in range(-1080, 1920, 70): d.line([x, 1080, x + 1080, 0], fill=(17, 27, 48), width=24)
        lg = logo(0.9); im.paste(lg, ((1920 - lg.width) // 2, (1080 - lg.height) // 2), lg)
        _logo_full = np.asarray(im).copy()
    return _logo_full

_X = np.arange(1920)[None, :].astype(np.float32); _Y = np.arange(1080)[:, None].astype(np.float32)
SKEW = 320
def ease(p): p = min(max(p, 0), 1); return 4 * p ** 3 if p < .5 else 1 - (-2 * p + 2) ** 3 / 2
def wipe(fr, p, phase):
    """phase 'in': panel covers left->right as p 0->1. phase 'out': panel leaves to the right as p 0->1."""
    pe = ease(p); u = _X - SKEW * (1 - _Y / 1080)
    if phase == 'in':
        E = -SKEW + pe * (1920 + SKEW); cov = u < E; edge = np.abs(u - E) < 16
    else:
        S = -SKEW + pe * (1920 + SKEW); cov = u > S; edge = np.abs(u - S) < 16
    out = fr.copy(); pnl = panel_image()
    out[cov] = pnl[cov]; out[edge & (u > -SKEW)] = YEL
    return out

_bug = None
def bug_layer():
    """small corner logo (top-right), RGBA float array full frame"""
    global _bug
    if _bug is None:
        L = Image.new('RGBA', (1920, 1080), (0, 0, 0, 0))
        lg = logo(0.32, tag=None)
        bb = lg.getbbox(); lg = lg.crop(bb)
        a = np.asarray(lg).astype(np.float32); a[..., 3] *= 0.85; lg = Image.fromarray(a.astype(np.uint8), 'RGBA')
        L.paste(lg, (1920 - lg.width - 50, 48), lg)
        _bug = np.asarray(L).astype(np.float32)
    return _bug

def over(base, ov):
    a = ov[..., 3:4] / 255.0
    return (base * (1 - a) + ov[..., :3] * a).astype(np.uint8)

if __name__ == '__main__':
    Image.fromarray(panel_image()).resize((960, 540)).save('brand_panel.png')
    fr = np.full((1080, 1920, 3), 120, np.uint8)
    Image.fromarray(over(wipe(fr, 0.5, 'in'), bug_layer())).resize((960, 540)).save('brand_wipe.png')
