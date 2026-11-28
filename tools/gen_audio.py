# tools/gen_audio.py —— 程序合成全部音效与音乐（numpy + 标准库 wave；音乐用 ffmpeg 转 ogg，没有 ffmpeg 就保留 wav）
"""用法： python -m tools.gen_audio      输出到 assets/audio/
音效：22.05 kHz 单声道 wav；音乐：32 kHz 立体声 ogg（可无缝循环）。想改风格就改这里的参数再运行。"""
import os, shutil, subprocess, sys, wave
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "audio")
SR = 22050
MSR = 32000
rng = np.random.RandomState(7)


def t_(dur, sr=SR): return np.arange(int(dur * sr)) / sr
def env_exp(n, k): return np.exp(-np.arange(n) / n * k)
def sine(f, t): return np.sin(2 * np.pi * f * t)


def lowpass(x, a):
    """一阶低通（a 越小越闷），用截断指数核卷积，免循环。"""
    n = int(min(len(x), 6 / max(a, 1e-3)))
    k = a * (1 - a) ** np.arange(max(n, 8))
    return np.convolve(x, k)[:len(x)]


def noise(n): return rng.uniform(-1, 1, n)
def norm(x, peak=0.9): return x / (np.max(np.abs(x)) + 1e-9) * peak


def fade(x, ms=4, sr=SR):
    n = int(ms / 1000 * sr)
    if n * 2 < len(x):
        x = x.copy(); x[:n] *= np.linspace(0, 1, n); x[-n:] *= np.linspace(1, 0, n)
    return x


def save_wav(name, x, sr=SR):
    x = np.clip(fade(x, 3, sr), -1, 1)
    with wave.open(os.path.join(OUT, name + ".wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((x * 32767).astype("<i2").tobytes())


# ---------------- 音效 ----------------
def bell(f, dur, amp=1.0, sr=SR):
    t = t_(dur, sr)
    e = np.exp(-t * 5.5 / dur)
    return amp * e * (sine(f, t) + 0.5 * sine(f * 2.76, t) * np.exp(-t * 9) + 0.3 * sine(f * 5.4, t) * np.exp(-t * 14))


def gun(dur, crack, thump_f, body, tail):
    n = int(dur * SR); t = t_(dur)
    c = lowpass(noise(n), crack) * env_exp(n, 22)
    th = sine(thump_f * np.exp(-t * 18), t) * env_exp(n, 12) * body
    ta = lowpass(noise(n), 0.04) * env_exp(n, tail) * 0.45
    return norm(c + th + ta)


def sfx():
    S = {}
    n = int(0.05 * SR); t = t_(0.05)
    S["click"] = norm(sine(1500, t) * env_exp(n, 14) + 0.4 * noise(n) * env_exp(n, 30), 0.5)
    S["shot_pistol"] = gun(0.22, 0.35, 140, 0.7, 9)
    S["shot_rifle"] = gun(0.26, 0.5, 110, 0.6, 8)
    S["shot_shotgun"] = gun(0.45, 0.28, 90, 1.1, 6)
    S["shot_smg"] = gun(0.12, 0.55, 170, 0.5, 14)
    S["shot_sniper"] = gun(0.8, 0.6, 70, 1.0, 4)
    n = int(0.45 * SR); t = t_(0.45)
    twang = sine(190 * (1 + 0.04 * np.exp(-t * 30)), t) + 0.5 * sine(380, t) + 0.25 * sine(570, t)
    hiss = lowpass(noise(n), 0.5) * np.exp(-t * 14) * 0.5
    S["shot_bow"] = norm(twang * np.exp(-t * 11) + hiss, 0.7)
    n = int(0.16 * SR); t = t_(0.16)
    S["melee"] = norm(lowpass(noise(n), 0.12) * env_exp(n, 12) + sine(95 * np.exp(-t * 14), t) * env_exp(n, 10), 0.8)
    n = int(0.35 * SR); t = t_(0.35)
    S["enemy_down"] = norm(sine(420 * np.exp(-t * 4.5), t) * env_exp(n, 6) + lowpass(noise(n), 0.2) * env_exp(n, 14) * 0.5, 0.7)
    d = np.concatenate([bell(392, 0.35, 0.8), bell(311, 0.35, 0.8), bell(233, 0.9, 0.9)[:int(0.8 * SR)]])
    pad = np.zeros(int(1.5 * SR)); pad[:len(d)] += 0
    o = np.zeros(int(1.5 * SR)); pos = 0
    for f, du in ((392, 0.35), (311, 0.35), (233, 0.9)):
        b = bell(f, du, 0.8); o[pos:pos + len(b)] += b; pos += int(0.3 * SR)
    S["colonist_down"] = norm(o[:int(1.4 * SR)], 0.7)
    o = np.zeros(int(0.8 * SR))
    for k, pos in enumerate((0, 0.18)):
        nn = int(0.08 * SR); tt = t_(0.08)
        o[int(pos * SR):int(pos * SR) + nn] += lowpass(noise(nn), 0.25) * env_exp(nn, 9) + sine(220 - k * 30, tt) * env_exp(nn, 8)
    for k, f in enumerate((660, 880)):
        b = bell(f, 0.45, 0.5); st = int((0.36 + k * 0.09) * SR); o[st:st + len(b)] += b[:len(o) - st]
    S["build_done"] = norm(o, 0.7)
    n = int(0.18 * SR); t = t_(0.18)
    S["harvest_done"] = norm(lowpass(noise(n), 0.3) * env_exp(n, 8) + sine(520 * np.exp(-t * 6), t) * env_exp(n, 9) * 0.6, 0.6)
    o = np.zeros(int(1.0 * SR))
    for k, f in enumerate((523, 659, 784)):
        b = bell(f, 0.5, 0.7); st = int(k * 0.11 * SR); o[st:st + len(b)] += b[:len(o) - st]
    S["quest_new"] = norm(o, 0.65)
    o = np.zeros(int(1.6 * SR))
    for k, f in enumerate((523, 659, 784, 1047)):
        b = bell(f, 0.9, 0.7); st = int(k * 0.12 * SR); o[st:st + len(b)] += b[:len(o) - st]
    b = bell(1568, 0.7, 0.35); o[int(0.5 * SR):int(0.5 * SR) + len(b)] += b
    S["quest_done"] = norm(o, 0.7)
    o = np.zeros(int(1.2 * SR)); t = t_(1.2)
    f = np.where((t * 2.5).astype(int) % 2 == 0, 740.0, 560.0)
    ph = np.cumsum(2 * np.pi * f / SR)
    w = np.sin(ph) + 0.35 * np.sin(2 * ph) + 0.2 * np.sin(3 * ph)
    S["alarm"] = norm(w * np.minimum(1, t * 30) * np.minimum(1, (1.2 - t) * 12), 0.6)
    n = int(2.0 * SR); t = t_(2.0)
    rumble = lowpass(noise(n), 0.015) * (np.minimum(1, t * 3) * np.exp(-t * 1.4))
    boom = sine(55 * np.exp(-t * 0.8), t) * np.exp(-t * 2.2)
    S["meteor"] = norm(rumble * 1.6 + boom, 0.9)

    # ---- 采集 / 脚步 / 落地 音效 ----
    def hp(x, a): return x - lowpass(x, a)

    def thock(f, dur, body=1.0, bright=0.0):
        n = int(dur * SR); t = t_(dur)
        x = sine(f * (1 + 0.25 * np.exp(-t * 40)), t) * env_exp(n, 9) * body
        x = x + lowpass(noise(n), 0.25) * env_exp(n, 20) * 0.7
        if bright: x = x + hp(noise(n), 0.3) * env_exp(n, 40) * bright
        return x

    def ring(f, dur, amp=1.0):
        t = t_(dur); n = len(t)
        return amp * (sine(f, t) * np.exp(-t * 14) + 0.6 * sine(f * 2.32, t) * np.exp(-t * 20)
                      + 0.4 * sine(f * 4.1, t) * np.exp(-t * 30) + 0.5 * hp(noise(n), 0.4) * np.exp(-t * 60))

    def place(o, start, x, g=1.0):
        i = int(start * SR); j = min(len(o), i + len(x))
        if i < len(o): o[i:j] += x[:j - i] * g

    S["hit_wood"] = norm(thock(210, 0.14, 1.0, 0.25), 0.7)
    n = int(0.12 * SR); t = t_(0.12)
    S["hit_stone"] = norm(hp(noise(n), 0.25) * env_exp(n, 30) + sine(1700, t) * env_exp(n, 26) * 0.5 + sine(820, t) * env_exp(n, 18) * 0.4, 0.7)
    S["hit_iron"] = norm(ring(1500, 0.3), 0.75)
    o = np.zeros(int(0.38 * SR)); place(o, 0, ring(760, 0.38, 1.0)); place(o, 0, thock(90, 0.2, 0.8))
    S["hit_meteor"] = norm(o, 0.8)
    o = np.zeros(int(0.3 * SR))
    for k, pos in enumerate((0.0, 0.1, 0.19)):
        nn = int(0.07 * SR); place(o, pos, lowpass(noise(nn), 0.6) * env_exp(nn, 8) * (0.9 - 0.2 * k))
    place(o, 0.2, sine(900, t_(0.04)) * env_exp(int(0.04 * SR), 14), 0.25)
    S["pick_berry"] = norm(o, 0.5)

    o = np.zeros(int(0.9 * SR))
    nn = int(0.06 * SR); place(o, 0.0, hp(noise(nn), 0.3) * env_exp(nn, 12) + thock(260, 0.06, 0.7))
    nn = int(0.5 * SR); tt = t_(0.5)
    place(o, 0.08, lowpass(noise(nn), 0.08) * np.sin(np.pi * np.minimum(1, tt / 0.5)) ** 1.5 * 0.8)
    place(o, 0.36, thock(65, 0.45, 1.6))
    S["done_tree"] = norm(o, 0.85)
    o = np.zeros(int(0.7 * SR))
    for pos, a in ((0, 1.0), (0.07, 0.8), (0.14, 0.7), (0.23, 0.55), (0.31, 0.4), (0.4, 0.3)):
        nn = int(0.09 * SR); tt = t_(0.09)
        place(o, pos, (hp(noise(nn), 0.2) * env_exp(nn, 22) + sine(600 + 700 * rng.rand(), tt) * env_exp(nn, 20) * 0.5), a)
    place(o, 0.0, thock(110, 0.25, 1.0))
    S["done_stone"] = norm(o, 0.8)
    o = np.zeros(int(0.9 * SR)); place(o, 0.0, ring(1300, 0.45, 1.1))
    for pos, a in ((0.1, 0.6), (0.2, 0.5), (0.3, 0.35)):
        nn = int(0.08 * SR); place(o, pos, hp(noise(nn), 0.2) * env_exp(nn, 24), a)
    S["done_iron"] = norm(o, 0.8)
    o = np.zeros(int(0.5 * SR))
    for pos in (0, 0.07, 0.14, 0.22):
        nn = int(0.08 * SR); place(o, pos, lowpass(noise(nn), 0.5) * env_exp(nn, 8), 0.8)
    place(o, 0.28, sine(780, t_(0.05)) * env_exp(int(0.05 * SR), 12), 0.3); place(o, 0.34, sine(980, t_(0.05)) * env_exp(int(0.05 * SR), 12), 0.25)
    S["done_berry"] = norm(o, 0.5)

    # 脚步：很轻，每步两种变体（名字带 2）
    def step_grass():
        n = int(0.09 * SR); return lowpass(noise(n), 0.12) * np.sin(np.pi * np.linspace(0, 1, n)) ** 1.2
    def step_dirt():
        n = int(0.08 * SR); return thock(120, 0.08, 0.9) + lowpass(noise(n), 0.3) * env_exp(n, 10) * 0.5
    def step_wood():
        return thock(170, 0.09, 1.0, 0.1)
    def step_stone():
        n = int(0.07 * SR); t = t_(0.07)
        return hp(noise(n), 0.25) * env_exp(n, 35) * 0.8 + sine(520, t) * env_exp(n, 30) * 0.5
    def step_metal():
        return ring(1100, 0.12, 0.8)
    def step_carpet():
        n = int(0.08 * SR); return lowpass(noise(n), 0.06) * env_exp(n, 9) * 0.8 + sine(80, t_(0.08)) * env_exp(n, 9) * 0.4
    for name, fn, peak in (("grass", step_grass, 0.28), ("dirt", step_dirt, 0.32), ("wood", step_wood, 0.34),
                           ("stone", step_stone, 0.32), ("metal", step_metal, 0.3), ("carpet", step_carpet, 0.22)):
        S["step_" + name] = norm(fn(), peak); S["step_" + name + "2"] = norm(fn(), peak * 0.9)

    # 物体落地：木头 = 两下"咚咚"，石头 = 闷响 + 碎石，金属 = 当啷，软物（肉/皮/布/食物）= 一声闷"噗"
    o = np.zeros(int(0.35 * SR)); place(o, 0.0, thock(150, 0.14, 1.2, 0.2)); place(o, 0.11, thock(190, 0.1, 0.9), 0.5)
    place(o, 0.19, thock(220, 0.08, 0.7), 0.25); S["drop_wood"] = norm(o, 0.6)
    o = np.zeros(int(0.4 * SR)); place(o, 0.0, thock(95, 0.2, 1.4, 0.3))
    for pos, a in ((0.08, 0.5), (0.14, 0.4), (0.2, 0.3)):
        nn = int(0.06 * SR); place(o, pos, hp(noise(nn), 0.2) * env_exp(nn, 24), a)
    S["drop_stone"] = norm(o, 0.65)
    o = np.zeros(int(0.6 * SR)); place(o, 0.0, ring(950, 0.4, 1.0)); place(o, 0.13, ring(1200, 0.3, 0.5)); place(o, 0.23, ring(1500, 0.2, 0.25))
    S["drop_metal"] = norm(o, 0.6)
    n = int(0.16 * SR); t = t_(0.16)
    S["drop_soft"] = norm(lowpass(noise(n), 0.1) * env_exp(n, 14) + sine(85 * np.exp(-t * 8), t) * env_exp(n, 10), 0.5)
    return S


# ---------------- 音乐 ----------------
def midi(m): return 440.0 * 2 ** ((m - 69) / 12)


def add(buf, start, x):
    i = int(start * MSR)
    if i >= len(buf): return
    j = min(len(buf), i + len(x)); buf[i:j] += x[:j - i]


def tone(f, dur, kind="pad", amp=1.0):
    t = t_(dur, MSR); n = len(t)
    if kind == "pad":
        a = np.minimum(1, t / 0.9) * np.minimum(1, (dur - t) / 1.1)
        x = sine(f, t) + 0.4 * sine(f * 2.003, t) + 0.15 * sine(f * 3.01, t) + 0.5 * sine(f * 0.998, t)
        return amp * a.clip(0) * x * 0.5
    if kind == "pluck":
        e = np.exp(-t * 4.0) * np.minimum(1, t / 0.006)
        return amp * e * (sine(f, t) + 0.45 * sine(2 * f, t) * np.exp(-t * 5) + 0.2 * sine(3 * f, t) * np.exp(-t * 8))
    if kind == "bell":
        e = np.exp(-t * 2.6)
        return amp * e * (sine(f, t) + 0.5 * sine(f * 2.76, t) * np.exp(-t * 4) + 0.25 * sine(f * 5.4, t) * np.exp(-t * 7))
    if kind == "bass":
        e = np.exp(-t * 3.2) * np.minimum(1, t / 0.01)
        return amp * e * (sine(f, t) + 0.5 * sine(2 * f, t) + 0.25 * sine(3 * f, t))
    if kind == "string":
        a = np.minimum(1, t / 0.25) * np.minimum(1, (dur - t) / 0.3)
        ph = 2 * np.pi * f * t
        x = sum(np.sin(ph * k + 0.3 * k) / k for k in range(1, 7)) + 0.6 * sum(np.sin(ph * 1.004 * k) / k for k in range(1, 5))
        return amp * a.clip(0) * x * 0.25
    return np.zeros(n)


def reverb(x, wet=0.28):
    out = x.copy()
    for d, g in ((0.073, 0.38), (0.121, 0.3), (0.197, 0.24), (0.311, 0.18), (0.467, 0.12)):
        k = int(d * MSR); out[k:] += x[:-k] * g * wet / 0.3 * 0.55
    return out


def make_loop(builder, bars, bpm, name, seed):
    r = np.random.RandomState(seed)
    beat = 60.0 / bpm; length = bars * 4 * beat
    tail = 2.5
    L = np.zeros(int((length + tail) * MSR)); R = np.zeros_like(L)
    builder(L, R, r, beat, bars)
    L = reverb(L); R = reverb(R)
    n = int(length * MSR)
    for ch in (L, R):                                       # 尾巴折回开头，循环处无缝
        m = len(ch) - n
        ch[:m] += ch[n:n + m]
    L, R = L[:n], R[:n]
    st = np.stack([L, R], axis=1)
    st = st / (np.max(np.abs(st)) + 1e-9) * 0.8
    pcm = (st * 32767).astype("<i2")
    wav = os.path.join(OUT, name + ".wav")
    with wave.open(wav, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(MSR); w.writeframes(pcm.tobytes())
    if shutil.which("ffmpeg"):
        ogg = os.path.join(OUT, name + ".ogg")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-c:a", "libvorbis", "-q:a", "3", ogg], check=True)
        os.remove(wav)


def pan(L, R, start, x, p):
    add(L, start, x * (1 - p) ** 0.5 * 1.2); add(R, start, x * p ** 0.5 * 1.2)


def day_builder(L, R, r, beat, bars):
    prog = [(57, [57, 60, 64]), (53, [53, 57, 60]), (48, [48, 52, 55]), (55, [55, 59, 62])]      # Am F C G
    scale = [60, 62, 64, 67, 69, 72, 74, 76]                                                        # C 大调五声
    for b in range(bars):
        root, tri = prog[b % 4]; t0 = b * 4 * beat
        for k, nt in enumerate(tri):
            pan(L, R, t0, tone(midi(nt), 4 * beat + 0.3, "pad", 0.55), 0.3 + 0.2 * k)
        add(L, t0, tone(midi(root - 12), 2 * beat, "bass", 0.5)); add(R, t0, tone(midi(root - 12), 2 * beat, "bass", 0.5))
        add(L, t0 + 2.5 * beat, tone(midi(root - 12 + 7), 1.5 * beat, "bass", 0.35))
        pos = 0.0
        while pos < 4 and (b % 2 == 0 or r.rand() < 0.8):
            if r.rand() < 0.62:
                near = [s for s in scale if abs(s - (tri[r.randint(0, 3)] + 12)) <= 5] or scale
                nt = near[r.randint(0, len(near))]
                pan(L, R, t0 + pos * beat, tone(midi(nt), 1.6, "pluck", 0.55), r.uniform(0.25, 0.75))
            pos += [0.5, 1.0, 1.0, 1.5][r.randint(0, 4)]


def night_builder(L, R, r, beat, bars):
    prog = [(45, [45, 52, 57]), (41, [41, 48, 53]), (43, [43, 50, 55]), (40, [40, 47, 52])]       # Am F G Em 低沉
    scale = [69, 72, 74, 76, 79, 81, 84]
    for b in range(bars):
        root, tri = prog[b % 4]; t0 = b * 4 * beat
        for k, nt in enumerate(tri):
            pan(L, R, t0, tone(midi(nt), 4 * beat + 0.6, "pad", 0.6), 0.2 + 0.3 * k)
        if b % 2 == 0:
            pan(L, R, t0 + 0.2, tone(midi(root + 12), 4 * beat, "pad", 0.3), 0.5)
        for _ in range(r.randint(1, 3)):
            nt = scale[r.randint(0, len(scale))]
            pan(L, R, t0 + r.uniform(0, 3.4) * beat, tone(midi(nt), 3.5, "bell", 0.34), r.uniform(0.15, 0.85))


def battle_builder(L, R, r, beat, bars):
    prog = [(50, [50, 53, 57]), (46, [46, 50, 53]), (43, [43, 46, 50]), (45, [45, 49, 52])]      # Dm Bb Gm A
    for b in range(bars):
        root, tri = prog[b % 4]; t0 = b * 4 * beat
        for k, nt in enumerate(tri):
            pan(L, R, t0, tone(midi(nt + 12), 4 * beat, "string", 0.6), 0.25 + 0.25 * k)
        for e in range(8):                                            # 八分音符低音
            f = midi(root - 12 + (7 if e % 4 == 3 else 0))
            x = tone(f, 0.45 * beat, "bass", 0.55); add(L, t0 + e * 0.5 * beat, x); add(R, t0 + e * 0.5 * beat, x)
        for q in range(4):                                            # 底鼓 / 军鼓 / 踩镲
            n = int(0.2 * MSR); t = np.arange(n) / MSR
            kick = sine(120 * np.exp(-t * 22) + 40, t) * np.exp(-t * 14)
            add(L, t0 + q * beat, kick * 0.9); add(R, t0 + q * beat, kick * 0.9)
            if q % 2 == 1:
                sn = lowpass(r.uniform(-1, 1, n), 0.25) * np.exp(-t * 18) * 0.5 + sine(190, t) * np.exp(-t * 20) * 0.3
                add(L, t0 + q * beat, sn); add(R, t0 + q * beat, sn)
        for e in range(8):
            n = int(0.05 * MSR); hh = r.uniform(-1, 1, n) * np.exp(-np.arange(n) / n * 6) * 0.14
            add(L, t0 + e * 0.5 * beat, hh); add(R, t0 + e * 0.5 * beat + 0.004, hh)
        if b % 2 == 1:
            for k, nt in enumerate((tri[0] + 24, tri[1] + 24, tri[2] + 24, tri[1] + 24)):
                pan(L, R, t0 + 2 * beat + k * 0.5 * beat, tone(midi(nt), 0.9, "pluck", 0.4), 0.3 + 0.13 * k)


def main():
    """python -m tools.gen_audio        重新生成全部（音效 + 音乐）
    python -m tools.gen_audio sfx    只重新生成音效（音乐不动，不需要 ffmpeg）"""
    only_sfx = len(sys.argv) > 1 and sys.argv[1] == "sfx"
    os.makedirs(OUT, exist_ok=True)
    s = sfx()
    for f in os.listdir(OUT):
        if f.endswith(".wav") and f[:-4] in s: os.remove(os.path.join(OUT, f))
        elif not only_sfx and f.endswith((".wav", ".ogg")) and f.startswith("music_"): os.remove(os.path.join(OUT, f))
    for k, v in s.items(): save_wav(k, v)
    if only_sfx:
        print(f"已重新生成 {len(s)} 个音效 → {OUT}"); return
    make_loop(day_builder, 16, 76, "music_day", 1)
    make_loop(night_builder, 12, 56, "music_night", 2)
    make_loop(battle_builder, 16, 118, "music_battle", 3)
    tot = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT))
    print(f"已生成 {len(os.listdir(OUT))} 个音频文件，共 {tot / 1024:.0f} KB → {OUT}")


if __name__ == "__main__":
    main()
