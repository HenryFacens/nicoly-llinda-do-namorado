"""Original synthesized music + sfx (numpy only). Writes intro_music.wav, outro_music.wav, whoosh.wav (48k stereo s16)."""
import numpy as np, wave
SR = 48000; BPM = 128; B = 60 / BPM
rng = np.random.default_rng(7)

def lp(x, fc):  # one-pole lowpass (fc may be array)
    fc = np.broadcast_to(np.asarray(fc, float), x.shape)
    a = np.exp(-2 * np.pi * fc / SR); y = np.empty_like(x); s = 0.0
    for i in range(len(x)): s = (1 - a[i]) * x[i] + a[i] * s; y[i] = s
    return y
def hp(x, fc): return x - lp(x, fc)
def note(n): return 440 * 2 ** ((n - 69) / 12)
def env(n, a, d):  # attack/decay in seconds, length n samples
    t = np.arange(n) / SR; e = np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / d); return e
def saw(f, n, ph=0):
    t = np.arange(n) / SR; return 2 * ((t * f + ph) % 1) - 1

def kick(n=int(0.45 * SR)):
    t = np.arange(n) / SR; f = 45 + 110 * np.exp(-t / 0.035)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.16) + 0.3 * rng.standard_normal(n) * np.exp(-t / 0.004)
def clap(n=int(0.25 * SR)):
    x = rng.standard_normal(n); x = hp(lp(x, 2500), 900)
    t = np.arange(n) / SR; e = np.exp(-t / 0.06) * (1 + 0.6 * (np.sin(2 * np.pi * 90 * t) > 0) * (t < 0.03))
    return x * e * 1.6
def hat(n=int(0.08 * SR)):
    x = hp(rng.standard_normal(n), 7000); return x * np.exp(-np.arange(n) / SR / 0.018) * 0.9

CH = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]  # Am F C G
ROOT = [45, 41, 48, 43]

def groove(beats, start_beat=0, sidechain=True, drums=True):
    n = int(beats * B * SR) + SR; L = np.zeros(n); R = np.zeros(n); duck = np.ones(n)
    for b in range(beats):
        i = int(b * B * SR); bar = (b + start_beat) // 4 % 4
        if drums:
            k = kick(); L[i:i + len(k)] += 0.9 * k; R[i:i + len(k)] += 0.9 * k
            dl = int(0.3 * SR); duck[i:i + dl] = np.minimum(duck[i:i + dl], 0.35 + 0.65 * np.linspace(0, 1, dl) ** 0.7)
            if (b + start_beat) % 2 == 1:
                c = clap(); L[i:i + len(c)] += 0.45 * c; R[i:i + len(c)] += 0.5 * c
            j = i + int(B / 2 * SR); h = hat(); L[j:j + len(h)] += 0.25 * h; R[j:j + len(h)] += 0.3 * h
        # bass: offbeat 8ths
        for s in (0.5,):
            j = i + int(s * B * SR); m = int(B / 2 * SR * 0.95)
            f = note(ROOT[bar] - 12); t = np.arange(m) / SR
            x = np.tanh(2.2 * np.sin(2 * np.pi * f * t)) * env(m, 0.004, 0.18)
            L[j:j + m] += 0.45 * x; R[j:j + m] += 0.45 * x
        # pluck arp 16ths
        for s in range(4):
            j = i + int(s * B / 4 * SR); m = int(0.2 * SR)
            nn = CH[bar][[0, 1, 2, 1][s]] + 12 + (12 if (b + s) % 3 == 0 else 0)
            x = lp(saw(note(nn), m) + 0.5 * saw(note(nn) * 1.005, m), 1800 + 3000 * np.exp(-np.arange(m) / SR / 0.04))
            x *= env(m, 0.002, 0.07); pan = 0.3 * np.sin(b + s)
            L[j:j + m] += 0.13 * x * (1 - pan); R[j:j + m] += 0.13 * x * (1 + pan)
    # pad chords per bar
    for b in range(0, beats, 4):
        i = int(b * B * SR); m = min(int(4 * B * SR), n - i); bar = (b + start_beat) // 4 % 4
        x = np.zeros(m)
        for nn in CH[bar]:
            for d in (-0.07, 0.07): x += saw(note(nn) * 2 ** (d / 12), m, rng.random())
        x = lp(x, 1400) * np.minimum(1, np.arange(m) / SR / 0.05)
        L[i:i + m] += 0.06 * x; R[i:i + m] += 0.06 * x[::-1] * 0 + 0.06 * x
    if sidechain:
        mus = duck; L *= mus; R *= mus
    return np.stack([L, R], 1)

def riser(dur):
    n = int(dur * SR); t = np.arange(n) / SR; p = t / dur
    x = lp(rng.standard_normal(n), 300 + 9000 * p ** 2) * p ** 2
    tone = np.sin(2 * np.pi * np.cumsum(200 + 900 * p ** 2) / SR) * p ** 3 * 0.25
    y = (x + tone) * 0.5; return np.stack([y, y], 1)
def impact(dur=2.0):
    n = int(dur * SR); t = np.arange(n) / SR
    boom = np.sin(2 * np.pi * np.cumsum(35 + 60 * np.exp(-t / 0.08)) / SR) * np.exp(-t / 0.5)
    crash = hp(rng.standard_normal(n), 4000) * np.exp(-t / 0.45) * 0.35
    L = boom + crash; R = boom + np.roll(crash, 240); return np.stack([L, R], 1)
def whoosh(dur=0.6):
    n = int(dur * SR); t = np.arange(n) / SR; p = t / dur
    e = np.sin(np.pi * p) ** 2
    fc = 400 + 5000 * np.sin(np.pi * p) ** 2
    x = lp(rng.standard_normal(n), fc) - lp(rng.standard_normal(n), fc * 0.2) * 0.3
    pan = np.linspace(-0.7, 0.7, n)
    return np.stack([x * e * (1 - pan), x * e * (1 + pan)], 1) * 0.8

def put(dst, src, t):
    i = int(t * SR); m = min(len(src), len(dst) - i); dst[i:i + m] += src[:m]

def norm(x, peak=0.89):
    return x / (np.abs(x).max() + 1e-9) * peak
def save(name, x):
    x = np.clip(x, -1, 1); w = wave.open(name, 'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((x * 32767).astype('<i2').tobytes()); w.close()

INTRO_BEATS = 15
if __name__ == '__main__':
    # intro: hit on beat 0, groove 15 beats, riser into impact at the episode start, tail
    tot = INTRO_BEATS * B + 2.2
    mix = np.zeros((int(tot * SR), 2))
    put(mix, impact(1.6) * 0.8, 0)
    g = groove(INTRO_BEATS); put(mix, g[:int(INTRO_BEATS * B * SR)], 0)
    put(mix, riser(3 * B) * 0.9, (INTRO_BEATS - 3) * B)
    put(mix, impact(2.2), INTRO_BEATS * B)
    # gentle pad tail under the opening line
    m = int(2.2 * SR); x = np.zeros(m)
    for nn in CH[0]: x += saw(note(nn), m) + saw(note(nn) * 1.004, m)
    x = lp(x, 900) * np.exp(-np.arange(m) / SR / 0.6) * 0.06; put(mix, np.stack([x, x], 1), INTRO_BEATS * B)
    mix = np.tanh(norm(mix, 1.0) * 1.3) * 0.85
    save('intro_music.wav', mix)
    # outro: 8 beats groove + final hit
    tot = 8 * B + 2.5; mix = np.zeros((int(tot * SR), 2))
    g = groove(8, start_beat=0); put(mix, g[:int(8 * B * SR)], 0)
    put(mix, impact(2.5), 8 * B)
    mix[:int(0.15 * SR)] *= np.linspace(0, 1, int(0.15 * SR))[:, None]
    mix = np.tanh(norm(mix, 1.0) * 1.3) * 0.85
    save('outro_music.wav', mix)
    save('whoosh.wav', norm(whoosh(), 0.8))
    print('ok', INTRO_BEATS * B)
