#!/usr/bin/env python3
"""Asset pipeline: procedural audio.

The same contract as every other generator in this folder — no raw stage, final
output written straight into `assets/processed/`, fully deterministic, one
shared vocabulary at the top that every recipe below is written in. What
`make_textures.py` is to pixels, this is to samples: the helpers between here
and RECIPES are the whole synthesis language of the game, and a new sound is a
short paragraph in it, never a new pile of DSP.

STDLIB ONLY. `wave`, `math`, `random`, `array`. Adding numpy here would buy
speed for an offline script that runs in under a minute and would put a
compiled dependency in the way of anybody regenerating the game's assets. Every
loop below is written to be read, not to be fast.

WHY FILES AND NOT WEB AUDIO. The client could synthesise all of this at runtime
and ship zero bytes. It would also be the only art in the game you cannot open
and listen to, iterating would mean reloading a browser instead of playing a
wav, and a zombie's growl would be a thirty-node graph rebuilt on every spawn.
Sounds are assets here for the same reason sprites are.

THREE RULES THE RECIPES ALL FOLLOW

  VARIANTS, NOT ONE SAMPLE. Anything that fires more than once a second —
  footsteps, shots, impacts, growls — is generated several times from different
  seeds and the client picks one and detunes it. A single sample replayed is
  the audible twin of `rng` per frame in a looping sprite sheet: each one is
  fine alone and the repetition is what you hear.

  LOOPS MUST CLOSE. A bed is rendered longer than it ships and `loopify` folds
  the tail back over the head, so the wrap is a crossfade instead of a click.
  Same discipline as a looping sprite sheet being a sine of the frame phase.

  THE MIX LIVES HERE. Per-sound gain, bus and loop flag go in the manifest, not
  in client code, exactly the way `anchorY` lives in the vfx manifest. There is
  one place to answer "why is the shot louder than the footstep".

Output (assets/processed/audio/):
    *.wav          16-bit mono PCM. One-shots at 22050 Hz, beds at 16000 Hz —
                   wind and fire have nothing above 8 kHz to lose and the beds
                   are by far the biggest files.
    manifest.json  name -> {files, gain, bus, loop}

Usage:
    python tools/make_audio.py
    python tools/make_audio.py --only shot,zombie-idle
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import wave
from array import array
from pathlib import Path

from make_textures import PROCESSED_DIR

# One-shots keep their top octave: a gunshot transient and a dry leaf are both
# mostly air above 8 kHz. Beds do not have it to begin with.
SFX_RATE = 22050
BED_RATE = 16000

#: Coefficients for a swept filter are recomputed every this many samples
#: rather than per sample. A sweep moves over tens of milliseconds and this is
#: under two, so the stepping is inaudible and the trig cost drops 32-fold.
COEF_BLOCK = 32

Buf = list[float]


# ---------------------------------------------------------------------------
# SOURCES
# ---------------------------------------------------------------------------


def silence(n: int) -> Buf:
    return [0.0] * n


def dur(seconds: float, rate: int) -> int:
    """Seconds -> samples. Never zero; a zero-length buffer breaks every helper."""
    return max(1, int(seconds * rate))


def white(n: int, rng: random.Random) -> Buf:
    return [rng.uniform(-1.0, 1.0) for _ in range(n)]


def pink(n: int, rng: random.Random) -> Buf:
    """Pink noise — equal energy per octave.

    White noise is the sound of a broken speaker; almost nothing in the world
    is flat. Wind, fire and distant rumble are all closer to pink, and starting
    from it means the filters below are shaping something that already has the
    right slope. Paul Kellet's three-pole economy approximation.
    """
    b0 = b1 = b2 = 0.0
    out = silence(n)
    for i in range(n):
        w = rng.uniform(-1.0, 1.0)
        b0 = 0.99765 * b0 + w * 0.0990460
        b1 = 0.96300 * b1 + w * 0.2965164
        b2 = 0.57000 * b2 + w * 1.0526913
        out[i] = (b0 + b1 + b2 + w * 0.1848) * 0.22
    return out


def brown(n: int, rng: random.Random, step: float = 0.035) -> Buf:
    """Brown noise — a random walk. The bottom of a drone or a distant boom."""
    out = silence(n)
    last = 0.0
    for i in range(n):
        last = max(-1.0, min(1.0, last * 0.996 + rng.uniform(-1.0, 1.0) * step))
        out[i] = last
    return out


def _shape(phase: float, kind: str, width: float) -> float:
    if kind == "sine":
        return math.sin(phase * math.tau)
    if kind == "tri":
        return 4.0 * abs(phase - 0.5) - 1.0
    if kind == "saw":
        return 2.0 * phase - 1.0
    if kind == "square":
        return 1.0 if phase < width else -1.0
    if kind == "pulse":
        # A narrow pulse is the cheapest glottal source there is: harmonically
        # rich, and the width is how "throaty" the voice sitting on top of the
        # formant filters comes out.
        return 1.0 if phase < width else -width / (1.0 - width)
    raise ValueError(f"unknown shape {kind}")


def tone(
    n: int,
    freq: float | object,
    rate: int,
    kind: str = "sine",
    width: float = 0.5,
    phase0: float = 0.0,
) -> Buf:
    """An oscillator. `freq` is a number, or a callable of normalized time.

    The callable form is what every sweep in this file is built on — a gunshot's
    punch dropping from 190 Hz to 45, a growl sagging as the breath runs out.
    Phase is accumulated, so a sweep never clicks the way retriggering would.
    """
    out = silence(n)
    phase = phase0
    denom = max(n - 1, 1)
    callable_freq = callable(freq)
    for i in range(n):
        f = freq(i / denom) if callable_freq else freq  # type: ignore[operator]
        phase += f / rate
        phase -= math.floor(phase)
        out[i] = _shape(phase, kind, width)
    return out


def lfo(
    n: int, rate: int, freq: float, depth: float, centre: float = 0.0, kind: str = "sine"
) -> Buf:
    """A slow control signal, as a buffer so it can multiply an audio one."""
    base = tone(n, freq, rate, kind)
    return [centre + v * depth for v in base]


# ---------------------------------------------------------------------------
# ENVELOPES
# ---------------------------------------------------------------------------


def env_perc(n: int, rate: int, attack: float, decay: float, curve: float = 3.0) -> Buf:
    """Fast in, curved out. The shape of anything struck, snapped or fired.

    `curve` above 1 makes the decay concave — loud for a moment then gone,
    which is what percussion actually does. A linear fade reads as a sound
    being turned down rather than a thing having happened.
    """
    out = silence(n)
    a = max(1, int(attack * rate))
    d = max(1, int(decay * rate))
    for i in range(n):
        if i < a:
            out[i] = i / a
        elif i < a + d:
            out[i] = (1.0 - (i - a) / d) ** curve
        else:
            out[i] = 0.0
    return out


def env_swell(n: int, rate: int, attack: float, hold: float, release: float) -> Buf:
    """In, stay, out. Breath, drones, and anything that has a duration."""
    out = silence(n)
    a = max(1, int(attack * rate))
    h = max(0, int(hold * rate))
    r = max(1, int(release * rate))
    for i in range(n):
        if i < a:
            out[i] = (i / a) ** 1.4
        elif i < a + h:
            out[i] = 1.0
        elif i < a + h + r:
            out[i] = (1.0 - (i - a - h) / r) ** 1.8
        else:
            out[i] = 0.0
    return out


def env_from(n: int, points: list[tuple[float, float]]) -> Buf:
    """Piecewise-linear envelope over normalized time. For custom shapes."""
    out = silence(n)
    denom = max(n - 1, 1)
    for i in range(n):
        t = i / denom
        prev_t, prev_v = points[0]
        value = prev_v
        for pt, pv in points[1:]:
            if t <= pt:
                span = max(pt - prev_t, 1e-6)
                value = prev_v + (pv - prev_v) * ((t - prev_t) / span)
                break
            prev_t, prev_v = pt, pv
            value = pv
        out[i] = value
    return out


# ---------------------------------------------------------------------------
# FILTERS
# ---------------------------------------------------------------------------


def _biquad_coefs(kind: str, freq: float, q: float, rate: int) -> tuple[float, ...]:
    """RBJ cookbook coefficients, normalized by a0."""
    freq = max(20.0, min(freq, rate * 0.45))
    w0 = math.tau * freq / rate
    cos_w0 = math.cos(w0)
    alpha = math.sin(w0) / (2.0 * max(q, 0.05))

    if kind == "lowpass":
        b0 = (1.0 - cos_w0) / 2.0
        b1 = 1.0 - cos_w0
        b2 = b0
    elif kind == "highpass":
        b0 = (1.0 + cos_w0) / 2.0
        b1 = -(1.0 + cos_w0)
        b2 = b0
    elif kind == "bandpass":
        b0 = alpha
        b1 = 0.0
        b2 = -alpha
    else:
        raise ValueError(f"unknown filter {kind}")

    a0 = 1.0 + alpha
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha
    return (b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)


def biquad(
    src: Buf, rate: int, kind: str, freq: float | object, q: float = 0.707
) -> Buf:
    """Second-order filter. `freq` may be a callable of normalized time.

    The swept form is the single most useful thing in this file. A noise burst
    whose lowpass falls from 3 kHz to 300 in sixty milliseconds is a gunshot;
    the same burst with a rising bandpass is a zip. Almost nothing here is a
    static filter.
    """
    n = len(src)
    out = silence(n)
    x1 = x2 = y1 = y2 = 0.0
    denom = max(n - 1, 1)
    is_swept = callable(freq)
    coefs = _biquad_coefs(kind, 1000.0 if is_swept else float(freq), q, rate)  # type: ignore[arg-type]

    for i in range(n):
        if is_swept and i % COEF_BLOCK == 0:
            coefs = _biquad_coefs(kind, freq(i / denom), q, rate)  # type: ignore[operator]
        b0, b1, b2, a1, a2 = coefs
        x0 = src[i]
        y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1 = x1, x0
        y2, y1 = y1, y0
        out[i] = y0
    return out


def dc_block(src: Buf, rate: int) -> Buf:
    """Remove any constant offset. A one-pole high-pass just above audible.

    Applied to every one-shot on the way out rather than fixed per recipe,
    because DC arrives from too many directions to audit: an asymmetric square
    wave has a non-zero mean by construction, an envelope can bias a burst, and
    a filter can leave a tail. Offset costs headroom, thumps on trigger, and —
    since levels are now set by measurement — quietly corrupts the loudness
    reading of everything it touches.
    """
    coeff = 1.0 - (math.tau * 8.0 / rate)
    out = silence(len(src))
    last_in = last_out = 0.0
    for i, x0 in enumerate(src):
        last_out = x0 - last_in + coeff * last_out
        last_in = x0
        out[i] = last_out
    return out


def onepole_lp(src: Buf, rate: int, freq: float) -> Buf:
    """A gentle 6 dB/oct tilt. For taking the glare off something, not shaping it."""
    a = math.exp(-math.tau * max(20.0, freq) / rate)
    out = silence(len(src))
    last = 0.0
    for i, v in enumerate(src):
        last = v * (1.0 - a) + last * a
        out[i] = last
    return out


# ---------------------------------------------------------------------------
# SPACE AND SATURATION
# ---------------------------------------------------------------------------


def reflections(src: Buf, rate: int, taps: list[tuple[float, float]], tail: float = 0.0) -> Buf:
    """Discrete echoes: trunks, not a room.

    A forest has no reverb in the concert-hall sense — it has a few hard slaps
    off trunks at wildly different distances and then nothing. Modelling that
    as a handful of delayed copies sounds far more like outdoors than a smooth
    tail does, and it is the difference between a gunshot fired in a wood and
    one fired in a stairwell.
    """
    extra = dur(tail, rate) if tail > 0 else 0
    out = list(src) + silence(extra)
    for delay, level in taps:
        offset = int(delay * rate)
        for i in range(len(src)):
            j = i + offset
            if j < len(out):
                out[j] += src[i] * level
    return out


def reverb(src: Buf, rate: int, room: float = 0.82, damp: float = 0.35, wet: float = 0.3) -> Buf:
    """Schroeder tail: four parallel combs into two allpasses.

    Used sparingly and always under `reflections`, never instead of it. This is
    the diffuse wash *behind* the slaps — the sound of a lot of small things
    scattering what is left.
    """
    n = len(src)
    combs = [0.0297, 0.0371, 0.0411, 0.0437]
    summed = silence(n)
    for delay in combs:
        size = max(1, int(delay * rate))
        buffer = [0.0] * size
        store = 0.0
        idx = 0
        for i in range(n):
            delayed = buffer[idx]
            summed[i] += delayed
            store = delayed * (1.0 - damp) + store * damp
            buffer[idx] = src[i] + store * room
            idx = (idx + 1) % size
    summed = [v * 0.25 for v in summed]

    for delay in (0.005, 0.0017):
        size = max(1, int(delay * rate))
        buffer = [0.0] * size
        idx = 0
        for i in range(n):
            delayed = buffer[idx]
            value = -summed[i] + delayed
            buffer[idx] = summed[i] + delayed * 0.5
            summed[i] = value
            idx = (idx + 1) % size

    return [src[i] * (1.0 - wet) + summed[i] * wet for i in range(n)]


def softclip(src: Buf, drive: float = 1.0) -> Buf:
    """Tanh saturation. Loudness without a digital edge.

    A gunshot that peaks at 1.0 and a gunshot that is *driven* into a limit are
    different sounds; the second one has weight. Everything percussive here
    goes through this before it is normalized.
    """
    return [math.tanh(v * drive) for v in src]


# ---------------------------------------------------------------------------
# ARRANGEMENT
# ---------------------------------------------------------------------------


def mix(*layers: Buf) -> Buf:
    n = max((len(layer) for layer in layers), default=0)
    out = silence(n)
    for layer in layers:
        for i, v in enumerate(layer):
            out[i] += v
    return out


def mul(a: Buf, b: Buf) -> Buf:
    """Elementwise. Applying an envelope, or ring-modulating two sources."""
    n = min(len(a), len(b))
    return [a[i] * b[i] for i in range(n)]


def gain(src: Buf, g: float) -> Buf:
    return [v * g for v in src]


def at(dst: Buf, src: Buf, offset: int, level: float = 1.0) -> Buf:
    """Drop `src` into `dst` starting at a sample offset, extending if needed."""
    end = offset + len(src)
    if end > len(dst):
        dst = dst + silence(end - len(dst))
    for i, v in enumerate(src):
        dst[offset + i] += v * level
    return dst


def pad(src: Buf, n: int) -> Buf:
    return src + silence(n - len(src)) if len(src) < n else src[:n]


def normalize(src: Buf, peak: float = 0.95) -> Buf:
    top = max((abs(v) for v in src), default=0.0)
    if top < 1e-9:
        return src
    return [v * (peak / top) for v in src]


def fade(src: Buf, rate: int, fade_in: float = 0.0, fade_out: float = 0.0) -> Buf:
    """Trim the ends to zero. Any buffer that starts or stops mid-cycle clicks."""
    out = list(src)
    n = len(out)
    a = int(fade_in * rate)
    for i in range(min(a, n)):
        out[i] *= i / max(a, 1)
    r = int(fade_out * rate)
    for i in range(min(r, n)):
        out[n - 1 - i] *= i / max(r, 1)
    return out


def loopify(src: Buf, rate: int, cross: float) -> Buf:
    """Fold the tail back over the head so the wrap is a crossfade.

    Render longer than you ship, then call this. The returned buffer is
    `cross` seconds shorter than what went in and its last sample leads back
    into its first — which is the only reason a bed can play for ten minutes
    without a tick every loop announcing its length.
    """
    n = len(src)
    c = max(1, int(cross * rate))
    if c >= n // 2:
        raise ValueError("crossfade must be well under half the buffer")
    out = src[: n - c]
    for i in range(c):
        k = i / c
        out[i] = src[i] * k + src[n - c + i] * (1.0 - k)
    return out


def scatter(
    n: int,
    rate: int,
    rng: random.Random,
    count: int,
    make: object,
    spread: tuple[float, float] = (0.0, 1.0),
) -> Buf:
    """Sprinkle `count` one-shots across a buffer. Crackle, chirps, splinters."""
    out = silence(n)
    lo, hi = spread
    for i in range(count):
        grain = make(rng, i)  # type: ignore[operator]
        offset = int((lo + rng.random() * (hi - lo)) * (n - 1))
        if offset + len(grain) <= n:
            out = at(out, grain, offset)
    return out


# ---------------------------------------------------------------------------
# OUTPUT
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# LOUDNESS
#
# Peak normalization is not loudness. Two files that both touch 0.97 can be
# ten decibels apart to the ear, because loudness is energy over time weighted
# by how the ear responds to frequency — which is why every hand-picked `gain`
# in this file used to be a guess that only sounded right next to whatever it
# was last compared against.
#
# So the levels are MEASURED. K-weighting from ITU-R BS.1770 (a high shelf for
# the head's response plus a high-pass that discounts sub-bass the ear barely
# registers as loudness), then the loudest 150 ms window — not the whole file.
# The window is the important choice: integrated loudness divides by duration,
# so it would call a 40 ms switch tick "quiet" and boost it into a bang, while
# rating a long quiet chime as loud. 150 ms is roughly the ear's own
# integration time, so a short sharp sound and a long soft one land where they
# actually sit.
# ---------------------------------------------------------------------------


def _k_weight(src: Buf, rate: int) -> Buf:
    """BS.1770 pre-filter, derived for any sample rate rather than tabulated."""
    # Stage 1: high shelf, +4 dB above ~1.7 kHz.
    f0, gain_db, q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    k = math.tan(math.pi * f0 / rate)
    vh = 10.0 ** (gain_db / 20.0)
    vb = vh**0.4996667741545416
    denom = 1.0 + k / q + k * k
    shelf = (
        (vh + vb * k / q + k * k) / denom,
        2.0 * (k * k - vh) / denom,
        (vh - vb * k / q + k * k) / denom,
        2.0 * (k * k - 1.0) / denom,
        (1.0 - k / q + k * k) / denom,
    )

    # Stage 2: RLB high-pass at ~38 Hz.
    f0, q = 38.13547087602444, 0.5003270373238773
    k = math.tan(math.pi * f0 / rate)
    denom = 1.0 + k / q + k * k
    highpass = (
        1.0,
        -2.0,
        1.0,
        2.0 * (k * k - 1.0) / denom,
        (1.0 - k / q + k * k) / denom,
    )

    out = src
    for b0, b1, b2, a1, a2 in (shelf, highpass):
        filtered = silence(len(out))
        x1 = x2 = y1 = y2 = 0.0
        for i, x0 in enumerate(out):
            y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
            x2, x1 = x1, x0
            y2, y1 = y1, y0
            filtered[i] = y0
        out = filtered
    return out


#: Ear integration window for the loudness measurement, in seconds.
LOUDNESS_WINDOW = 0.15


def loudness_lufs(src: Buf, rate: int) -> float:
    """Loudest 150 ms of `src`, K-weighted, in LUFS. -inf for silence."""
    weighted = _k_weight(src, rate)
    window = max(1, int(LOUDNESS_WINDOW * rate))
    squares = [v * v for v in weighted]

    if len(squares) <= window:
        # Shorter than the window: still divide by the FULL window, so a very
        # short sound is correctly measured as carrying less energy than a
        # sustained one rather than being judged on its peak alone.
        total = sum(squares)
        best = total / window
    else:
        total = sum(squares[:window])
        best = total
        for i in range(window, len(squares)):
            total += squares[i] - squares[i - window]
            if total > best:
                best = total
        best /= window

    if best <= 1e-12:
        return float("-inf")
    return -0.691 + 10.0 * math.log10(best)


def save_wav(path: Path, src: Buf, rate: int) -> int:
    """16-bit mono PCM. Returns bytes written."""
    pcm = array("h", (int(max(-1.0, min(1.0, v)) * 32767) for v in src))
    if sys.byteorder == "big":
        pcm.byteswap()
    raw = pcm.tobytes()
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(raw)
    return len(raw) + 44


# ===========================================================================
# RECIPES
#
# Everything below is written in the vocabulary above. A recipe takes a seeded
# rng and returns (samples, rate). Nothing below allocates a filter, and
# nothing below should need to.
# ===========================================================================


# --- interface -------------------------------------------------------------
#
# THE MENU AND THE LOBBY CHROME ARE SILENT. There is no hover tick and no click,
# and both were tried and cut. Hover chattered at buttons the pointer was only
# crossing; the click marked a decision the screen was already announcing, and
# on a title screen that opens onto a crackling bonfire it was a synthetic
# noise sitting on top of the one thing that sells the place. What is left here
# is not interface decoration — it is the game refusing you (`ui-error`) and
# the bag, which is a thing on your back rather than a panel.


def ui_error(rng: random.Random) -> tuple[Buf, int]:
    """Two low buzzes. A refusal, not an alarm — the bag is full, nobody died."""
    rate = SFX_RATE
    n = dur(0.26, rate)
    out = silence(n)
    for beat in (0.0, 0.11):
        m = dur(0.075, rate)
        buzz = mul(
            tone(m, 104.0, rate, "square", width=0.42),
            env_perc(m, rate, 0.004, 0.065, 1.8),
        )
        out = at(out, biquad(buzz, rate, "lowpass", 1400), int(beat * rate))
    return normalize(softclip(out, 1.3), 0.48), rate


def ui_bag_open(rng: random.Random) -> tuple[Buf, int]:
    """Canvas and a buckle. The bag is a thing on your back, not a panel."""
    rate = SFX_RATE
    n = dur(0.28, rate)
    cloth = biquad(white(n, rng), rate, "bandpass", lambda t: 700 + 1500 * t, 1.1)
    cloth = mul(cloth, env_from(n, [(0.0, 0.0), (0.08, 1.0), (0.5, 0.45), (1.0, 0.0)]))
    buckle = biquad(white(dur(0.03, rate), rng), rate, "bandpass", 4200, 3.0)
    buckle = mul(buckle, env_perc(len(buckle), rate, 0.001, 0.026, 3.0))
    return normalize(mix(gain(cloth, 0.9), at(silence(n), buckle, int(0.02 * rate), 0.5)), 0.45), rate


def ui_bag_close(rng: random.Random) -> tuple[Buf, int]:
    rate = SFX_RATE
    n = dur(0.22, rate)
    cloth = biquad(white(n, rng), rate, "bandpass", lambda t: 1900 - 1200 * t, 1.1)
    cloth = mul(cloth, env_from(n, [(0.0, 0.0), (0.06, 1.0), (0.4, 0.5), (1.0, 0.0)]))
    thud = mul(tone(n, 120.0, rate, "sine"), env_perc(n, rate, 0.002, 0.09, 3.0))
    return normalize(mix(gain(cloth, 0.7), gain(thud, 0.5)), 0.45), rate


# --- the camp --------------------------------------------------------------


def _fire_spit(rate: int, rng: random.Random, scale: float = 1.0) -> Buf:
    """One pop of sap letting go. The grain both fire sounds are built from.

    Shared rather than written twice, for the same reason the drawing helpers
    are shared: the bonfire you sit next to and the bonfire that roars when the
    party commits have to be made of the same material, or the second one reads
    as a different fire being cut to.
    """
    m = dur((0.006 + rng.random() * 0.035) * scale, rate)
    pop = biquad(white(m, rng), rate, "bandpass", 1200 + rng.random() * 2600, 2.2)
    return gain(mul(pop, env_perc(m, rate, 0.0005, 0.02 * scale, 3.5)), 0.35 + rng.random() * 0.65)


def _fire_roar(n: int, rate: int, rng: random.Random, cutoff: float = 520.0) -> Buf:
    """The steady half: air and heat, with no transients in it."""
    roar = biquad(pink(n, rng), rate, "lowpass", cutoff, 0.8)
    return mix(roar, gain(biquad(brown(n, rng), rate, "lowpass", 180), 0.5))


def bed_fire(rng: random.Random) -> tuple[Buf, int]:
    """The bonfire. The camp's whole sound bed, and the thing you walk away from.

    Two parts that have to stay separate: a low roar that is almost steady, and
    crackle that is entirely not. Crackle alone reads as a fault in the audio;
    roar alone reads as traffic. The slow LFO on the roar is the fire breathing.
    """
    rate = BED_RATE
    cross = 0.9
    n = dur(5.0 + cross, rate)

    roar = mul(_fire_roar(n, rate, rng), lfo(n, rate, 0.31, 0.22, 0.78))
    crackle = scatter(n, rate, rng, 150, lambda r, _i: _fire_spit(rate, r))
    body = mix(gain(roar, 0.75), gain(crackle, 0.55))
    return normalize(loopify(body, rate, cross), 0.72), rate


def sfx_kindle(rng: random.Random) -> tuple[Buf, int]:
    """The fire answering the match.

    IT IS THE SAME FIRE, ALL AT ONCE. This used to be a whoosh with a low boom
    under it, which is the sound of an explosion, not of a hearth — the fire
    you are sitting next to and the fire that answers you had nothing in common
    but a name. So it is built from `_fire_roar` and `_fire_spit`, the same two
    parts as the bed: the roar swells hard and falls away, and the crackle
    arrives as a dense burst rather than a sprinkle.

    Timed to `make_vfx.py`'s kindle sheet — 16 frames at 16 fps is one second
    and the visual impact lands at 0.48 of it, so the roar peaks there.
    """
    rate = SFX_RATE
    n = dur(2.0, rate)
    impact = int(0.48 * rate)

    # The pit gathering itself: the roar rises INTO the impact, opening up as
    # it goes, so the peak is arrived at rather than cut to.
    roar = _fire_roar(n, rate, rng, cutoff=900.0)
    roar = mul(
        roar,
        env_from(
            n,
            [
                (0.0, 0.06),
                (impact / n * 0.55, 0.42),
                (impact / n, 1.0),
                (impact / n + 0.14, 0.62),
                (1.0, 0.0),
            ],
        ),
    )

    # A brighter band on top for the moment of the flare — a big fire has
    # treble a small one does not, and this is what makes it read as bigger
    # rather than merely louder.
    flare_n = n - impact
    flare = biquad(pink(flare_n, rng), rate, "bandpass", lambda t: 2400 - 1700 * t, 0.8)
    flare = mul(flare, env_perc(flare_n, rate, 0.02, 0.9, 2.0))

    # Crackle, dense and front-loaded: everything in the pit letting go at once.
    crackle = scatter(n, rate, rng, 90, lambda r, _i: _fire_spit(rate, r, 1.4), spread=(0.24, 0.72))

    out = mix(gain(roar, 1.0), at(silence(n), gain(flare, 0.4), impact), gain(crackle, 0.7))
    return normalize(softclip(out, 1.5), 0.92), rate


def sfx_summon(rng: random.Random) -> tuple[Buf, int]:
    """A player arriving at the fire. SUBTLE — it is a greeting, not an event.

    This is the sound that plays every time anybody joins, including four
    people filing into a room in ten seconds, so it has to survive repetition.
    The earlier version had a hard strike, a sub drop and a bell on top, which
    was a fine one-off and exhausting on the fourth arrival. What is left is a
    soft rise and a settle: no transient to speak of, no low end, and a peak
    well below every other sound in the game.

    Still aligned to the summon sheet (14 frames at 14 fps, impact at 0.52) —
    the settle lands where the column does, it just does not hit.
    """
    rate = SFX_RATE
    n = dur(1.3, rate)
    impact = int(0.52 * rate)

    # A quiet rising chord, mostly air. Fifths and octaves only: anything with
    # a third in it starts sounding like a jingle.
    charge = silence(impact)
    for partial, level in ((1.0, 0.4), (1.5, 0.26), (2.0, 0.16)):
        sweep = tone(impact, lambda t, p=partial: (260.0 + 300.0 * t**1.4) * p, rate, "sine")
        charge = mix(charge, gain(sweep, level))
    charge = mul(charge, env_from(impact, [(0.0, 0.0), (0.55, 0.45), (1.0, 0.8)]))

    # The settle: a breath of filtered noise closing, with a soft tone under
    # it. No percussion — the sprite already flashes on this frame, and two
    # things landing at once is what made the old one feel like a hit.
    settle_n = n - impact
    breath = biquad(white(settle_n, rng), rate, "bandpass", lambda t: 1800 - 1100 * t, 0.9)
    breath = mul(breath, env_from(settle_n, [(0.0, 0.0), (0.08, 0.7), (0.4, 0.3), (1.0, 0.0)]))
    hum = mul(tone(settle_n, 392.0, rate, "sine"), env_perc(settle_n, rate, 0.02, 0.55, 2.6))

    out = at(silence(n), gain(charge, 0.5), 0)
    out = at(out, gain(breath, 0.3), impact)
    out = at(out, gain(hum, 0.34), impact)
    return normalize(out, 0.42), rate


def sfx_ready(rng: random.Random) -> tuple[Buf, int]:
    """Two notes up. Somebody at the fire said yes."""
    rate = SFX_RATE
    n = dur(0.4, rate)
    out = silence(n)
    for offset, freq in ((0.0, 392.0), (0.09, 587.3)):
        m = dur(0.3, rate)
        note = mix(
            gain(mul(tone(m, freq, rate, "sine"), env_perc(m, rate, 0.004, 0.26, 3.0)), 1.0),
            gain(mul(tone(m, freq * 2.0, rate, "sine"), env_perc(m, rate, 0.003, 0.13, 4.0)), 0.25),
        )
        out = at(out, note, int(offset * rate))
    return normalize(out, 0.5), rate


def sfx_unready(rng: random.Random) -> tuple[Buf, int]:
    rate = SFX_RATE
    n = dur(0.34, rate)
    out = silence(n)
    for offset, freq in ((0.0, 523.3), (0.08, 349.2)):
        m = dur(0.24, rate)
        note = mul(tone(m, freq, rate, "sine"), env_perc(m, rate, 0.004, 0.2, 3.0))
        out = at(out, note, int(offset * rate))
    return normalize(out, 0.42), rate


# --- leaving, and arriving -------------------------------------------------


def sfx_void(rng: random.Random) -> tuple[Buf, int]:
    """The corridor out of the camp.

    Played under the march. It is deliberately almost nothing — a low swell and
    the fire falling away behind it. The point of the walk-out is that the
    warmth stops; a big sound here would fill the hole the fire left, which is
    exactly the hole the player is supposed to feel.
    """
    rate = BED_RATE
    n = dur(3.4, rate)
    drone = mix(
        gain(mul(tone(n, lambda t: 48.0 - 6.0 * t, rate, "sine"), env_swell(n, rate, 1.1, 1.2, 1.1)), 0.9),
        gain(mul(tone(n, lambda t: 72.5 - 9.0 * t, rate, "tri"), env_swell(n, rate, 1.4, 0.8, 1.2)), 0.35),
    )
    air = biquad(pink(n, rng), rate, "bandpass", lambda t: 260 + 340 * t, 0.7)
    air = mul(air, env_swell(n, rate, 1.6, 0.6, 1.2))
    return normalize(mix(drone, gain(air, 0.5)), 0.66), rate


def sfx_siren(rng: random.Random) -> tuple[Buf, int]:
    """One turn of an extraction pad's alarm.

    THE ONLY REPEATING ONE-SHOT IN THE CATALOG. It plays once per sweep of the
    corner lamps for the whole thirteen seconds of a pickup, so its length is
    not a taste decision: 12 frames at 16 fps out of `siren.png` is 0.75s, and
    a tick that did not land on the sweep would be a second alarm playing under
    the one on screen.

    It is a MECHANICAL siren, not an electronic one — a rotor forcing air
    through a horn, which is why the pitch glides rather than steps and why the
    horn's own resonance is a swept bandpass rather than a fixed tone. Two
    partials a fifth apart is what stops it reading as a test tone; the tiny
    tremolo is the rotor's blades passing the port, and it is the single detail
    that makes the sound feel like it is coming out of a machine bolted to
    something.

    It has to survive being heard from across a dark map with a horde walking
    in, so it is deliberately mid-forward and a little harsh. This is the sound
    of the party having told the forest exactly where they are.
    """
    rate = SFX_RATE
    n = dur(0.75, rate)
    # Up fast, down slower: a rotor spun up by a motor that then coasts. A
    # symmetric sweep is a police car; this one has weight in it.
    def glide(t: float) -> float:
        rise = 1.0 - (1.0 - min(t / 0.42, 1.0)) ** 2 if t < 0.42 else 1.0
        fall = 0.0 if t < 0.42 else ((t - 0.42) / 0.58) ** 1.4
        return 300.0 + 340.0 * rise - 300.0 * fall

    body = mix(
        gain(tone(n, glide, rate, "saw"), 0.62),
        gain(tone(n, lambda t: glide(t) * 1.5, rate, "tri"), 0.30),
        gain(tone(n, lambda t: glide(t) * 0.5, rate, "sine"), 0.34),
    )
    # The horn: a resonance that tracks the pitch, which is what a flared throat
    # does to whatever is driven through it.
    body = biquad(body, rate, "bandpass", lambda t: glide(t) * 1.15, 0.9)
    # Blades passing the port. Fast, shallow, and the whole reason it sounds
    # driven rather than played.
    body = mul(body, lfo(n, rate, 34.0, 0.14, 0.86))
    body = mul(body, env_from(n, [(0.0, 0.0), (0.10, 1.0), (0.62, 0.92), (1.0, 0.0)]))
    # It is outdoors and it is loud, so it comes back off the treeline.
    body = reflections(body, rate, [(0.11, 0.24), (0.19, 0.14)])
    return normalize(softclip(body, 1.35), 0.88), rate


def sfx_arrive(rng: random.Random) -> tuple[Buf, int]:
    """The day names itself. One deep hit with the wood of the forest in it."""
    rate = SFX_RATE
    n = dur(2.4, rate)
    hit = mul(
        tone(n, lambda t: 96.0 - 60.0 * t**0.5, rate, "sine"),
        env_perc(n, rate, 0.004, 1.5, 2.0),
    )
    knock = biquad(white(dur(0.09, rate), rng), rate, "lowpass", lambda t: 2400 - 2000 * t)
    knock = mul(knock, env_perc(len(knock), rate, 0.001, 0.08, 2.5))
    body = mix(gain(hit, 0.95), pad(gain(knock, 0.5), n))
    body = reflections(body, rate, [(0.07, 0.28), (0.13, 0.18), (0.23, 0.11)])
    return normalize(softclip(body, 1.25), 0.9), rate


# --- the forest ------------------------------------------------------------


def bed_wind(rng: random.Random) -> tuple[Buf, int]:
    """Wind in the canopy. The floor under every forest level.

    The cutoff wanders on two LFOs at unrelated rates. One would give a pulse
    you can count, and once you can count it the forest becomes a machine.
    """
    rate = BED_RATE
    cross = 1.2
    n = dur(7.0 + cross, rate)

    drift = lfo(n, rate, 0.07, 380.0, 720.0)
    gust = lfo(n, rate, 0.17, 210.0, 0.0)
    cutoff = [max(140.0, drift[i] + gust[i]) for i in range(n)]

    source = pink(n, rng)
    voiced = biquad(source, rate, "bandpass", lambda t: cutoff[min(int(t * (n - 1)), n - 1)], 0.75)
    low = biquad(source, rate, "lowpass", 240, 0.7)

    swell = [0.55 + 0.45 * v for v in lfo(n, rate, 0.11, 1.0, 0.0)]
    body = mix(gain(mul(voiced, swell), 0.85), gain(low, 0.4))
    return normalize(loopify(body, rate, cross), 0.55), rate


def bed_night(rng: random.Random) -> tuple[Buf, int]:
    """What is alive out there and what is not.

    Sparse. The gaps are the content — a chirp every few seconds says the wood
    is full of things; a continuous chorus says you are listening to a sound
    file. There is a very low hum under it that never resolves into anything,
    which is the whole job of this layer.
    """
    rate = BED_RATE
    cross = 1.0
    n = dur(9.0 + cross, rate)

    hum = mix(
        gain(mul(tone(n, 41.0, rate, "sine"), lfo(n, rate, 0.05, 0.3, 0.7)), 0.55),
        gain(biquad(brown(n, rng), rate, "lowpass", 120), 0.6),
    )

    def chirp(local_rng: random.Random, _index: int) -> Buf:
        m = dur(0.05 + local_rng.random() * 0.05, rate)
        base = 2400.0 + local_rng.random() * 1400.0
        cry = tone(m, lambda t, b=base: b * (1.0 + 0.12 * math.sin(t * 26.0)), rate, "sine")
        return gain(mul(cry, env_perc(m, rate, 0.006, 0.05, 2.0)), 0.18 + local_rng.random() * 0.3)

    insects = scatter(n, rate, rng, 26, chirp)

    def creak(local_rng: random.Random, _index: int) -> Buf:
        m = dur(0.35 + local_rng.random() * 0.4, rate)
        grind = biquad(
            white(m, local_rng),
            rate,
            "bandpass",
            lambda t: 220 + 120 * math.sin(t * 9.0),
            7.0,
        )
        return gain(mul(grind, env_swell(m, rate, 0.12, 0.1, 0.3)), 0.5)

    timber = scatter(n, rate, rng, 3, creak)

    body = mix(gain(hum, 0.7), gain(insects, 0.5), gain(timber, 0.35))
    return normalize(loopify(body, rate, cross), 0.42), rate


def bed_rain(rng: random.Random) -> tuple[Buf, int]:
    """Rain on a forest canopy. The night's other coat.

    Three layers, because a hiss alone is static and a drop-only bed is a
    leaky tap. The WASH is the weather — broadband, wandering, never quite
    the same two seconds in a row. The BODY is rain hitting leaves, a
    low wet weight that makes the hiss belong to a place. The DROPS are
    the ones that land near you: sparse, close, and the reason you believe
    the rest.

    The gaps between close drops are the content, same as the night chirps.
    A continuous patter says you are listening to a sound file.
    """
    rate = BED_RATE
    cross = 1.4
    n = dur(8.5 + cross, rate)

    source = pink(n, rng)
    # Two LFOs at unrelated rates so the hiss never pulses on a count.
    drift = lfo(n, rate, 0.07, 2200.0, 3400.0)
    gust = lfo(n, rate, 0.19, 900.0, 0.0)
    cutoff = [max(1400.0, drift[i] + gust[i]) for i in range(n)]
    wash = biquad(source, rate, "bandpass", lambda t: cutoff[min(int(t * (n - 1)), n - 1)], 0.85)
    # A slower swell so the rain breathes like a front passing, not a fan.
    swell = [0.62 + 0.38 * v for v in lfo(n, rate, 0.08, 1.0, 0.0)]
    wash = mul(wash, swell)

    canopy = biquad(brown(n, rng, 0.028), rate, "lowpass", 380, 0.65)
    canopy = mul(canopy, [0.7 + 0.3 * v for v in lfo(n, rate, 0.11, 1.0, 0.0)])

    def drop(local_rng: random.Random, index: int) -> Buf:
        # Close rain: a short bright tick with a wet tail. Heavier ones are
        # rarer and last a breath longer — a drop on a leaf, not a tap.
        heavy = index % 7 == 0
        m = dur((0.045 if heavy else 0.028) + local_rng.random() * 0.04, rate)
        tick = biquad(
            white(m, local_rng),
            rate,
            "bandpass",
            2400 + local_rng.random() * (1800 if heavy else 2800),
            1.6 if heavy else 2.4,
        )
        tick = mul(tick, env_perc(m, rate, 0.0008, 0.04 if heavy else 0.022, 2.8))
        if heavy:
            body = biquad(white(m, local_rng), rate, "lowpass", 700)
            body = mul(body, env_perc(m, rate, 0.001, 0.05, 2.4))
            tick = mix(gain(tick, 1.0), gain(body, 0.55))
        return gain(tick, 0.28 + local_rng.random() * (0.55 if heavy else 0.35))

    drops = scatter(n, rate, rng, 64, drop, spread=(0.04, 0.96))

    def cluster(local_rng: random.Random, _index: int) -> Buf:
        # A handful of drops arriving together — rain does that, a file does not.
        span = dur(0.18 + local_rng.random() * 0.16, rate)
        out = silence(span)
        count = 3 + int(local_rng.random() * 3)
        for i in range(count):
            grain = drop(local_rng, i + 3)
            offset = int(local_rng.random() * max(span - len(grain), 1))
            out = at(out, grain, offset, 0.7 + local_rng.random() * 0.4)
        return out

    bursts = scatter(n, rate, rng, 7, cluster, spread=(0.08, 0.9))

    body = mix(
        gain(wash, 0.78),
        gain(canopy, 0.55),
        gain(drops, 0.85),
        gain(bursts, 0.7),
    )
    return normalize(loopify(body, rate, cross), 0.52), rate


def sfx_dread(rng: random.Random, variant: int) -> tuple[Buf, int]:
    """Something out there, once in a while. Never attached to a real enemy.

    A branch going somewhere you are not looking. This is the cheapest fear in
    the game and it works precisely because it is a lie — the player turns, and
    the fact that nothing is there is the point.
    """
    rate = SFX_RATE
    n = dur(0.9, rate)
    snap_n = dur(0.05, rate)
    snap = biquad(white(snap_n, rng), rate, "bandpass", 900 + variant * 420, 2.4)
    snap = mul(snap, env_perc(snap_n, rate, 0.0008, 0.045, 3.0))
    rustle = biquad(white(dur(0.5, rate), rng), rate, "bandpass", 2600, 1.2)
    rustle = mul(rustle, env_from(len(rustle), [(0.0, 0.0), (0.15, 0.6), (1.0, 0.0)]))

    out = at(silence(n), snap, int(0.02 * rate), 0.9)
    out = at(out, rustle, int(0.06 * rate), 0.35)
    out = reflections(out, rate, [(0.09, 0.22), (0.17, 0.12)])
    return normalize(out, 0.5), rate


# --- the player ------------------------------------------------------------


def sfx_step_soft(rng: random.Random, variant: int) -> tuple[Buf, int]:
    """Boot on turf. Weight first, texture second."""
    rate = SFX_RATE
    n = dur(0.16, rate)
    thud = biquad(white(n, rng), rate, "lowpass", lambda t: 520 - 260 * t, 1.0)
    thud = mul(thud, env_perc(n, rate, 0.002, 0.075 + rng.random() * 0.03, 2.6))
    body = mul(tone(n, 74.0 + rng.random() * 16.0, rate, "sine"), env_perc(n, rate, 0.002, 0.05, 3.0))
    grit = biquad(white(dur(0.05, rate), rng), rate, "bandpass", 3000, 1.4)
    grit = mul(grit, env_perc(len(grit), rate, 0.001, 0.045, 2.6))
    out = mix(gain(thud, 0.9), gain(body, 0.55), pad(gain(grit, 0.22), n))
    return normalize(softclip(out, 1.2), 0.55), rate


def sfx_step_litter(rng: random.Random, variant: int) -> tuple[Buf, int]:
    """Boot on dry leaves. Same weight, a lot more surface."""
    rate = SFX_RATE
    n = dur(0.24, rate)
    thud = biquad(white(n, rng), rate, "lowpass", 460, 1.0)
    thud = mul(thud, env_perc(n, rate, 0.002, 0.06, 2.8))

    def crunch(local_rng: random.Random, _index: int) -> Buf:
        m = dur(0.004 + local_rng.random() * 0.012, rate)
        tick = biquad(white(m, local_rng), rate, "bandpass", 2200 + local_rng.random() * 3600, 2.6)
        return gain(mul(tick, env_perc(m, rate, 0.0004, 0.01, 3.0)), 0.4 + local_rng.random() * 0.6)

    leaves = scatter(n, rate, rng, 14, crunch, spread=(0.0, 0.55))
    out = mix(gain(thud, 0.8), gain(leaves, 0.75))
    return normalize(softclip(out, 1.15), 0.55), rate


def sfx_shot(rng: random.Random, variant: int) -> tuple[Buf, int]:
    """The gun. The most-heard sound in the game, so it gets the most layers.

    THE BODY OF A GUNSHOT IS LOW-MID, NOT TREBLE. Both earlier versions got
    this wrong from opposite directions — the first buried everything under
    500 Hz and read as a thump in a box, the second answered that by pushing
    the energy up to 2.5-5 kHz and read as a thin hiss with a disconnected
    thud. Four reference recordings (`assets/inspiration/gun/`) analysed
    through an FFT say both were wrong in the same place: real shots put
    24-44% of their energy between 150 Hz and 1 kHz, and 85% of it below
    ~2.5 kHz. The second version had 3.6% in that band and needed 4.9 kHz to
    reach 85%. The hole in the middle was the whole problem.

    Target, averaged across the references and leaning on the two that are
    single clean shots rather than long ambient ones:

        <150  150-400  400-1k  1k-2.5k  2.5-5k  5-10k
         ~28      ~18     ~22      ~15     ~10     ~5

    Five layers:
      CRACK   the transient. Short and QUIET — it is what makes the shot sound
              close, not what makes it sound loud, and at the old level it was
              half the spectrum.
      BODY    the report itself: broad noise sweeping 1400 -> 380 Hz. This is
              the layer that was missing.
      BOOM    lowpassed noise under it, filling below 400.
      PUNCH   a sine dropping 230 -> 95 Hz. Chest.
      TAIL    slaps off trunks, LOWPASSED — air and foliage eat the top, so a
              tail as bright as the direct sound reads as a tiled room.
    """
    rate = SFX_RATE
    n = dur(0.7, rate)

    # EACH LAYER OWNS A DIFFERENT BAND. That is the discipline that took two
    # attempts to find: when the punch, the boom and the body all had content
    # around 200-400 Hz they summed into a 58% spike there and starved both the
    # sub and the report. Every layer below is placed so its mass lands
    # somewhere the others are not.
    crack_n = dur(0.009, rate)
    crack = biquad(white(crack_n, rng), rate, "highpass", 2600, 0.7)
    crack = mul(crack, env_perc(crack_n, rate, 0.0002, 0.008, 2.0))

    # The report — owns 400 Hz to 1 kHz. Broad Q on purpose: a narrow band here
    # whistles, and the references show a wide shelf rather than a peak. The
    # sweep is placed by where the ENERGY lands, not where it starts: the
    # envelope is mostly spent in the first thirty milliseconds, so a sweep
    # beginning at 2.2 kHz leaves this band empty however low it ends.
    body_n = dur(0.13, rate)
    body = biquad(white(body_n, rng), rate, "bandpass", lambda t: 1150 - 700 * t**0.5, 0.5)
    body = mul(body, env_perc(body_n, rate, 0.0006, 0.095, 2.4))

    # Owns 150-400. Nothing was targeting this band, and the references all
    # have real content in it.
    low_n = dur(0.15, rate)
    low = biquad(white(low_n, rng), rate, "bandpass", 265, 0.6)
    low = mul(low, env_perc(low_n, rate, 0.0008, 0.11, 2.2))

    # Under 150. Cut low enough that it does not crowd the report — and kept
    # QUIET, because `normalize` scales by peak and the peak is set by the
    # bass: every dB added down here shrinks everything else in the file.
    boom_n = dur(0.18, rate)
    boom = biquad(white(boom_n, rng), rate, "lowpass", lambda t: 190 - 95 * t, 0.8)
    boom = mul(boom, env_perc(boom_n, rate, 0.0008, 0.13, 2.2))

    # A thin band of definition up top. Small — this is seasoning, and it was
    # the main course last time.
    mid_n = dur(0.07, rate)
    mid = biquad(white(mid_n, rng), rate, "bandpass", 2700, 1.0)
    mid = mul(mid, env_perc(mid_n, rate, 0.001, 0.055, 2.4))

    # Chest. Starts just above the sub and falls straight through it, so it
    # crosses 150-400 rather than sitting in it.
    punch_n = dur(0.12, rate)
    punch = mul(
        tone(punch_n, lambda t: 165.0 - 112.0 * t**0.45, rate, "sine"),
        env_perc(punch_n, rate, 0.001, 0.09, 2.4),
    )

    dry = mix(
        pad(gain(crack, 0.55), n),
        pad(gain(body, 1.0), n),
        pad(gain(low, 0.95), n),
        pad(gain(boom, 0.3), n),
        pad(gain(mid, 0.24), n),
        pad(gain(punch, 0.26), n),
    )
    dry = softclip(dry, 2.2)

    # Longer and darker than before: the references decay to -40 dB over
    # 0.3-0.6 s, and their tails carry almost nothing above 2 kHz.
    wet = reflections(
        dry,
        rate,
        [(0.013, 0.26), (0.031, 0.22), (0.058, 0.16), (0.104, 0.11), (0.163, 0.07)],
    )
    wet = mix(wet, gain(reverb(pad(dry, len(wet)), rate, room=0.8, damp=0.55, wet=1.0), 0.2))
    wet = biquad(wet, rate, "lowpass", 7800, 0.7)
    return normalize(pad(wet, n), 0.97), rate


def sfx_shotgun(rng: random.Random, variant: int) -> tuple[Buf, int]:
    """A shell. The same five layers as `sfx_shot`, moved down and given room.

    PITCH ALONE DOES NOT MAKE A SHOTGUN. The catalog ships one gunshot and
    eleven weapons, and `WeaponDef.shot_pitch` is what keeps a P90 and a
    Deagle from being the same event — but a shell played at 0.72x is a rifle
    in slow motion, because slowing a sample stretches the CRACK along with
    everything else and the crack is the part that says "small". What a
    twelve-gauge actually is, next to a rifle round, is:

      * far more mass under 150 Hz, and it arrives a beat LATER than the
        transient rather than with it — you hear the bang and then feel it;
      * a much longer, darker tail, because a shell dumps its energy into the
        air rather than down a rifled barrel;
      * almost no 2-5 kHz definition. A shotgun is not a crack, it is a WHUMP.

    Two variants, and the caller does not force one: unlike the knife, whose
    variant IS the combo step, both of these are the same weapon and picking
    between them is only there to stop a pumped magazine sounding like a
    loop.
    """
    rate = SFX_RATE
    n = dur(1.1, rate)

    # The transient, and it is SOFTER than a rifle's. What makes a shell sound
    # close is the low end arriving, not the click.
    crack_n = dur(0.012, rate)
    crack = biquad(white(crack_n, rng), rate, "highpass", 1800, 0.7)
    crack = mul(crack, env_perc(crack_n, rate, 0.0004, 0.011, 2.0))

    # The report, swept lower and slower than the rifle's 1150 -> 450.
    body_n = dur(0.20, rate)
    body = biquad(white(body_n, rng), rate, "bandpass", lambda t: 780 - 470 * t**0.5, 0.5)
    body = mul(body, env_perc(body_n, rate, 0.0008, 0.15, 2.1))

    # 120-300 Hz, which is where the weight of a shell lives.
    low_n = dur(0.26, rate)
    low = biquad(white(low_n, rng), rate, "bandpass", 190, 0.6)
    low = mul(low, env_perc(low_n, rate, 0.001, 0.20, 2.0))

    # The sub, DELAYED by a few milliseconds so the mass lands behind the
    # transient instead of on it. That gap is most of the difference between
    # a big gun and a loud one.
    boom_n = dur(0.34, rate)
    boom = biquad(white(boom_n, rng), rate, "lowpass", lambda t: 150 - 80 * t, 0.8)
    boom = mul(boom, env_perc(boom_n, rate, 0.004, 0.26, 2.0))

    # Chest, an octave under the rifle's.
    punch_n = dur(0.22, rate)
    punch = mul(
        tone(punch_n, lambda t: 108.0 - 72.0 * t**0.45, rate, "sine"),
        env_perc(punch_n, rate, 0.0015, 0.17, 2.2),
    )

    dry = mix(
        pad(gain(crack, 0.34), n),
        pad(gain(body, 1.0), n),
        pad(gain(low, 1.05), n),
        pad(gain(boom, 0.42), n),
        pad(gain(punch, 0.34), n),
    )
    dry = softclip(dry, 2.0)

    # Longer and darker than a rifle's tail: more energy, less of it up top.
    wet = reflections(
        dry,
        rate,
        [(0.017, 0.30), (0.039, 0.25), (0.071, 0.19), (0.128, 0.13), (0.201, 0.09)],
    )
    wet = mix(wet, gain(reverb(pad(dry, len(wet)), rate, room=0.86, damp=0.62, wet=1.0), 0.26))
    wet = biquad(wet, rate, "lowpass", 5200, 0.7)
    return normalize(pad(wet, n), 0.97), rate


def sfx_hurt(rng: random.Random, variant: int) -> tuple[Buf, int]:
    """Taking a hit. An impact and the breath it knocks out."""
    rate = SFX_RATE
    n = dur(0.5, rate)
    impact = biquad(white(dur(0.09, rate), rng), rate, "lowpass", lambda t: 1500 - 1150 * t)
    impact = mul(impact, env_perc(len(impact), rate, 0.001, 0.08, 2.4))
    thump = mul(
        tone(n, lambda t: 130.0 - 70.0 * t, rate, "sine"), env_perc(n, rate, 0.002, 0.16, 2.6)
    )
    breath_n = dur(0.34, rate)
    breath = biquad(white(breath_n, rng), rate, "bandpass", 620 + variant * 90, 2.0)
    breath = mul(breath, env_from(breath_n, [(0.0, 0.0), (0.12, 1.0), (1.0, 0.0)]))
    out = mix(pad(gain(impact, 0.9), n), gain(thump, 0.8), at(silence(n), gain(breath, 0.4), int(0.05 * rate)))
    return normalize(softclip(out, 1.5), 0.85), rate


def bed_heartbeat(rng: random.Random) -> tuple[Buf, int]:
    """Two thumps and a wait. Loops at rest; the client speeds it up as HP drops."""
    rate = BED_RATE
    n = dur(1.15, rate)
    out = silence(n)
    for offset, level in ((0.0, 1.0), (0.21, 0.68)):
        m = dur(0.3, rate)
        beat = mul(
            tone(m, lambda t: 62.0 - 26.0 * t, rate, "sine"), env_perc(m, rate, 0.006, 0.2, 2.4)
        )
        sub = mul(tone(m, 33.0, rate, "sine"), env_perc(m, rate, 0.01, 0.16, 2.0))
        out = at(out, mix(gain(beat, 1.0), gain(sub, 0.6)), int(offset * rate), level)
    return normalize(fade(out, rate, 0.004, 0.02), 0.8), rate


# --- the lantern -----------------------------------------------------------


def _switch_tick(rng: random.Random, centre: float, decay: float) -> tuple[Buf, int]:
    """A switch, and nothing else.

    Both lantern sounds used to carry an electrical coil swelling up or dying
    away underneath, which made switching the lamp on a small event. It is not
    an event — it is a thumb moving a piece of plastic, and the light doing
    something is what the player is looking at. Two ticks, one a little duller
    than the other so on and off are distinguishable with your eyes closed.
    """
    rate = SFX_RATE
    n = dur(decay + 0.02, rate)
    body = biquad(white(n, rng), rate, "bandpass", centre, 1.8)
    snap = biquad(white(n, rng), rate, "highpass", 4200)
    out = mix(gain(body, 1.0), gain(snap, 0.35))
    return normalize(mul(out, env_perc(n, rate, 0.0004, decay, 3.4)), 0.5), rate


def sfx_lantern_on(rng: random.Random) -> tuple[Buf, int]:
    """Brighter and shorter — the positive half of the switch."""
    return _switch_tick(rng, 2900.0, 0.016)


def sfx_lantern_off(rng: random.Random) -> tuple[Buf, int]:
    """Duller and a touch longer. Same switch, travelling the other way."""
    return _switch_tick(rng, 1700.0, 0.022)


def sfx_lantern_flicker(rng: random.Random) -> tuple[Buf, int]:
    """The battery failing. A stutter in the coil, not a beep.

    A UI beep would tell the player a number is low. This tells them the lamp
    in their hand is dying, which is the same information and a different
    feeling.
    """
    rate = SFX_RATE
    n = dur(0.3, rate)
    coil = tone(n, 620.0, rate, "tri")
    stutter = env_from(n, [(0.0, 0.0), (0.05, 0.8), (0.18, 0.05), (0.3, 0.7), (0.55, 0.0), (0.7, 0.4), (1.0, 0.0)])
    hiss = biquad(white(n, rng), rate, "bandpass", 3400, 1.8)
    out = mix(gain(mul(coil, stutter), 0.5), gain(mul(hiss, stutter), 0.3))
    return normalize(biquad(out, rate, "lowpass", 3000), 0.4), rate


# --- zombies ---------------------------------------------------------------
#
# All four zombie sounds are one instrument: a narrow pulse train through three
# bandpass formants, with noise mixed into the source for breath. That is a
# crude vocal tract, and crude is right — these should sound like something
# that used to have a voice and does not any more. The variations between idle,
# alert, attack and death are the pitch contour and the envelope, nothing else,
# which is also why they sound like they come from the same throat.


def _wander(n: int, rate: int, rng: random.Random, amount: float, hz: float = 80.0) -> Buf:
    """A 1.0-centred random walk. Irregularity, not vibrato.

    THIS IS WHAT KEEPS A GROWL FROM BEING A MOO. A cow is a clean pitch with a
    smooth contour; the only difference between that and a throat which no
    longer works is cycle-to-cycle instability. A sine wobble sounds like a
    singer, however deep you set it. A random walk sounds broken, which is the
    one we want.
    """
    steps = max(2, int(n / max(1.0, rate / hz)))
    points = [1.0 + rng.uniform(-amount, amount) for _ in range(steps + 2)]
    out = silence(n)
    for i in range(n):
        pos = i / n * steps
        k = int(pos)
        frac = pos - k
        out[i] = points[k] * (1.0 - frac) + points[k + 1] * frac
    return out


def _throat(
    n: int,
    rate: int,
    rng: random.Random,
    freq: object,
    breath: float,
    formants: tuple[tuple[float, float, float], ...],
    width: float = 0.16,
    rough: float = 0.0,
    sub: float = 0.0,
) -> Buf:
    """The one instrument every zombie sound is played on.

    A narrow pulse train through bandpass formants, with noise mixed into the
    source for breath — a crude vocal tract, and crude is right for something
    that used to have a voice and does not any more. `rough` and `sub` are what
    make it a growl rather than a note: instability in the pitch, and a layer
    an octave down that the ear reads as a torn throat instead of a low one.
    """
    denom = max(n - 1, 1)
    base = freq
    if rough > 0.0:
        wobble = _wander(n, rate, rng, rough)
        raw = freq

        def base(t: float) -> float:  # noqa: F811 - deliberate shadow
            value = raw(t) if callable(raw) else raw  # type: ignore[operator]
            return value * wobble[min(int(t * denom), n - 1)]

    source = mix(
        gain(tone(n, base, rate, "pulse", width=width), 1.0 - breath),
        gain(biquad(white(n, rng), rate, "bandpass", 1100, 0.7), breath),
    )
    if sub > 0.0:
        # Period doubling. Real growls, screams and creaky voices all do this —
        # the vocal folds fall into a two-cycle pattern and the octave below
        # appears. It is the single most "animal" thing available here.
        def halved(t: float) -> float:
            value = base(t) if callable(base) else base  # type: ignore[operator]
            return value * 0.5

        source = mix(source, gain(tone(n, halved, rate, "pulse", width=width * 1.5), sub))

    voiced = silence(n)
    for centre, q, level in formants:
        voiced = mix(voiced, gain(biquad(source, rate, "bandpass", centre, q), level))
    return biquad(voiced, rate, "lowpass", 3600, 0.8)


def _grind(n: int, rate: int, rng: random.Random, depth: float = 0.45) -> Buf:
    """Irregular amplitude, from filtered noise rather than an LFO.

    Same argument as `_wander`, one dimension over: a clean tremolo is a
    musical effect and a wandering one is a body.
    """
    rectified = [abs(v) for v in white(n, rng)]
    slow = normalize(onepole_lp(rectified, rate, 11.0), 1.0)
    return [(1.0 - depth) + depth * v for v in slow]


def sfx_zombie_idle(rng: random.Random, variant: int) -> tuple[Buf, int]:
    """The growl you hear before you see anything. Played positionally.

    This is the horror of the game. It is low, it is long, and it comes out of
    the dark from a direction — the client pans and attenuates it by distance,
    so the sound alone tells you roughly where and roughly how far, and the
    lantern tells you the rest only if you point it there.
    """
    rate = SFX_RATE
    length = 0.85 + rng.random() * 0.3
    n = dur(length, rate)
    # Well clear of cattle. Under about 70 Hz with a smooth contour this stops
    # being a growl and becomes livestock — the earlier 56 Hz version was a
    # moo with a filter on it, and no amount of formant tuning saved it. The
    # rasp comes from `rough` and `sub`, not from going lower.
    f0 = 84.0 + rng.random() * 34.0

    def contour(t: float) -> float:
        return f0 * (1.0 - 0.16 * t**1.4)

    body = _throat(
        n,
        rate,
        rng,
        contour,
        breath=0.5,
        # Tighter and lower than a vowel: a throat, not a mouth saying
        # something. The top band is deliberately noisy rasp rather than a
        # formant, which is where the "wet" comes from.
        formants=((255.0, 2.3, 1.0), (740.0, 2.8, 0.62), (2500.0, 2.6, 0.34)),
        width=0.11,
        # Roughness carries the growl; the subharmonic only seasons it. Pushed
        # much past this the octave-down becomes the strongest periodic
        # component in the sound, the ear hears THAT as the pitch, and the
        # variant lands back in cattle territory — which is exactly how the
        # first version failed, one layer further down.
        rough=0.22,
        sub=0.24,
    )
    shape = mul(env_swell(n, rate, 0.09, length - 0.36, 0.28), _grind(n, rate, rng, 0.5))
    return normalize(softclip(mul(body, shape), 1.8), 0.75), rate


def sfx_zombie_alert(rng: random.Random, variant: int) -> tuple[Buf, int]:
    """It has you. Pitch rises instead of sagging — the one contour that reads
    as intent rather than as a body making noise."""
    rate = SFX_RATE
    n = dur(0.66, rate)
    f0 = 104.0 + rng.random() * 30.0

    def contour(t: float) -> float:
        return f0 * (1.0 + 0.62 * t**1.2)

    body = _throat(
        n,
        rate,
        rng,
        contour,
        breath=0.5,
        formants=((400.0, 2.4, 1.0), (1350.0, 2.8, 0.72), (3000.0, 3.0, 0.45)),
        width=0.09,
        # Rougher than the idle: committing tears the voice further.
        rough=0.22,
        sub=0.3,
    )
    shape = mul(
        env_from(n, [(0.0, 0.0), (0.1, 0.75), (0.5, 1.0), (0.78, 0.8), (1.0, 0.0)]),
        _grind(n, rate, rng, 0.3),
    )
    return normalize(softclip(mul(body, shape), 2.0), 0.85), rate


def sfx_zombie_attack(rng: random.Random, variant: int) -> tuple[Buf, int]:
    """The swing, and it is a SLASH — an arm cutting air, not a monster talking.

    The blade is a narrow band of noise whose centre sweeps up and back down in
    under a fifth of a second. That arc is the whole effect: a band that only
    rises reads as a zip, and a static one reads as a hiss. The snarl is an
    accent underneath at less than half the level — the earlier version had it
    at 0.9 against a 0.4 swish, which is why it read as a growl with some wind
    behind it instead of as a hit coming at you.
    """
    rate = SFX_RATE
    n = dur(0.34, rate)

    # Up and back down, peaking about a third of the way in. `sin(pi t)` is the
    # arc; the exponent skews the peak early so the fastest part of the swing
    # is at the start, the way an arm actually moves.
    def sweep(t: float) -> float:
        arc = math.sin(min(1.0, t * 1.25) * math.pi) ** 0.65
        return 600.0 + 5400.0 * arc

    air = biquad(white(n, rng), rate, "bandpass", sweep, 2.0)
    air = mul(air, env_from(n, [(0.0, 0.0), (0.14, 1.0), (0.42, 0.5), (1.0, 0.0)]))

    # A second, brighter edge a beat later: two things passing, not one tube.
    edge = biquad(white(n, rng), rate, "bandpass", lambda t: 2600 + 3800 * t, 3.2)
    edge = mul(edge, env_from(n, [(0.0, 0.0), (0.2, 0.85), (0.48, 0.18), (1.0, 0.0)]))

    f0 = 116.0 + rng.random() * 34.0
    snarl = _throat(
        n,
        rate,
        rng,
        lambda t: f0 * (1.0 + 0.28 * t),
        breath=0.55,
        formants=((480.0, 2.2, 1.0), (1500.0, 2.6, 0.7)),
        width=0.09,
        rough=0.24,
        sub=0.28,
    )
    snarl = mul(snarl, env_from(n, [(0.0, 0.0), (0.05, 1.0), (0.3, 0.35), (1.0, 0.0)]))

    out = mix(gain(air, 1.0), gain(edge, 0.55), gain(snarl, 0.42))
    return normalize(softclip(out, 1.7), 0.88), rate


def sfx_zombie_hit(rng: random.Random, variant: int) -> tuple[Buf, int]:
    """A round landing in a body. Wet, short, and low — never a metal ping."""
    rate = SFX_RATE
    n = dur(0.3, rate)
    slap = biquad(white(dur(0.05, rate), rng), rate, "lowpass", lambda t: 1900 - 1500 * t)
    slap = mul(slap, env_perc(len(slap), rate, 0.0006, 0.045, 2.2))
    squelch = biquad(white(dur(0.16, rate), rng), rate, "bandpass", lambda t: 900 - 620 * t, 3.4)
    squelch = mul(squelch, env_perc(len(squelch), rate, 0.002, 0.14, 2.6))
    thud = mul(
        tone(n, lambda t: 112.0 - 58.0 * t, rate, "sine"), env_perc(n, rate, 0.002, 0.12, 2.8)
    )
    out = mix(pad(gain(slap, 1.0), n), pad(gain(squelch, 0.55), n), gain(thud, 0.7))
    return normalize(softclip(out, 1.8), 0.8), rate


def sfx_zombie_death(rng: random.Random, variant: int) -> tuple[Buf, int]:
    """The growl collapsing. Pitch falls through the floor, then a body lands.

    The thud sits on the death sheet's impact (`DEATH_IMPACT` in make_vfx.py).
    The sheet is 12 frames at 16 fps, so that flash is 0.36 s in — moving the
    land here means the sound and the sprite hit the floor together.
    """
    rate = SFX_RATE
    n = dur(0.95, rate)
    f0 = 100.0 + rng.random() * 26.0
    body = _throat(
        n,
        rate,
        rng,
        lambda t: f0 * (1.0 - 0.5 * t**0.7),
        breath=0.52,
        formants=((300.0, 2.4, 1.0), (860.0, 2.8, 0.5), (2200.0, 2.8, 0.2)),
        width=0.11,
        # Roughness climbs as it goes: the voice comes apart on the way down.
        rough=0.3,
        sub=0.26,
    )
    body = mul(body, env_from(n, [(0.0, 0.0), (0.05, 1.0), (0.32, 0.55), (0.55, 0.12), (0.82, 0.0)]))
    fall = biquad(white(dur(0.22, rate), rng), rate, "lowpass", lambda t: 900 - 700 * t)
    fall = mul(fall, env_perc(len(fall), rate, 0.003, 0.18, 2.4))
    drop = mul(tone(dur(0.28, rate), 58.0, rate, "sine"), env_perc(dur(0.28, rate), rate, 0.004, 0.24, 2.4))
    # Wet slap: the body opening on the floor, not just a thud.
    slap_n = dur(0.16, rate)
    slap = biquad(white(slap_n, rng), rate, "bandpass", lambda t: 1100 - 700 * t, 1.4)
    slap = mul(slap, env_perc(slap_n, rate, 0.001, 0.12, 2.6))
    out = at(silence(n), body, 0)
    # 0.36 s — DEATH_IMPACT * (DEATH_FRAMES / DEATH_FPS).
    land = int(0.36 * rate)
    out = at(out, mix(gain(fall, 0.7), gain(drop, 0.85), gain(slap, 0.65)), land)
    return normalize(softclip(out, 1.4), 0.82), rate


# --- loot, crates, pockets -------------------------------------------------


def sfx_loot(rng: random.Random) -> tuple[Buf, int]:
    """The physical half of a pickup: a thing leaving the ground and hitting cloth."""
    rate = SFX_RATE
    n = dur(0.26, rate)
    lift = biquad(white(dur(0.07, rate), rng), rate, "bandpass", lambda t: 1400 + 1800 * t, 1.4)
    lift = mul(lift, env_perc(len(lift), rate, 0.002, 0.06, 2.2))
    pocket = biquad(white(dur(0.12, rate), rng), rate, "lowpass", 900)
    pocket = mul(pocket, env_perc(len(pocket), rate, 0.003, 0.1, 2.6))
    return normalize(mix(pad(gain(lift, 0.6), n), at(silence(n), gain(pocket, 0.8), int(0.08 * rate))), 0.55), rate


def sfx_rarity(rng: random.Random, tier: int) -> tuple[Buf, int]:
    """The musical half of a pickup: one chime per rarity.

    Five tiers, and they are the same instrument getting more of itself. Common
    is a single short note; legendary is four notes, a shimmering octave above,
    and a tail three times as long. The player learns this in one session and
    from then on knows what they picked up before the tooltip has drawn —
    which is the entire reason it is five sounds and not one.
    """
    rate = SFX_RATE
    # A pentatonic climb, so any prefix of it is consonant on its own.
    scale = (523.25, 659.25, 783.99, 1046.50)
    notes = (1, 1, 2, 3, 4)[tier]
    spacing = (0.0, 0.0, 0.075, 0.068, 0.062)[tier]
    decay = (0.28, 0.38, 0.5, 0.72, 1.1)[tier]
    shimmer = (0.0, 0.0, 0.12, 0.22, 0.34)[tier]
    n = dur(spacing * notes + decay + 0.15, rate)

    out = silence(n)
    for index in range(notes):
        freq = scale[index % len(scale)] * (1.0 if tier < 4 else 1.0 + 0.002 * index)
        m = dur(decay + 0.1, rate)
        note = mul(tone(m, freq, rate, "sine"), env_perc(m, rate, 0.003, decay, 3.2))
        # A slightly detuned partial an octave up: metal, not a test tone.
        note = mix(
            note,
            gain(mul(tone(m, freq * 2.005, rate, "sine"), env_perc(m, rate, 0.002, decay * 0.5, 4.0)), 0.28),
        )
        if shimmer > 0.0:
            note = mix(
                note,
                gain(
                    mul(tone(m, freq * 3.01, rate, "sine"), env_perc(m, rate, 0.002, decay * 0.35, 5.0)),
                    shimmer,
                ),
            )
        out = at(out, note, int(index * spacing * rate), 1.0 / (1.0 + index * 0.25))

    if tier >= 3:
        out = mix(out, gain(reverb(out, rate, room=0.75, damp=0.4, wet=1.0), 0.18))
    return normalize(out, 0.5 + tier * 0.05), rate


def sfx_coin(rng: random.Random) -> tuple[Buf, int]:
    """Metal. Two inharmonic partials and a very short strike."""
    rate = SFX_RATE
    n = dur(0.4, rate)
    out = silence(n)
    for freq, level, decay in ((2100.0, 1.0, 0.22), (3170.0, 0.55, 0.16), (4830.0, 0.3, 0.1)):
        ring = mul(tone(n, freq, rate, "sine"), env_perc(n, rate, 0.0008, decay, 3.6))
        out = mix(out, gain(ring, level))
    strike = biquad(white(dur(0.006, rate), rng), rate, "highpass", 4000)
    out = mix(out, pad(gain(mul(strike, env_perc(len(strike), rate, 0.0003, 0.005, 2.0)), 0.5), n))
    return normalize(out, 0.45), rate


def sfx_crate_break(rng: random.Random, variant: int) -> tuple[Buf, int]:
    """Dry wood letting go. Splinters scattered over a body hit, not one crack.

    Timed against the crate smash sheet (8 frames at 12 fps = 0.67 s): the
    splinters land inside that window so the sound stops when the sprite does.
    """
    rate = SFX_RATE
    n = dur(0.75, rate)

    body = biquad(white(dur(0.16, rate), rng), rate, "lowpass", lambda t: 2200 - 1800 * t, 1.0)
    body = mul(body, env_perc(len(body), rate, 0.001, 0.14, 2.4))
    boom = mul(tone(n, lambda t: 140.0 - 88.0 * t, rate, "sine"), env_perc(n, rate, 0.002, 0.2, 2.6))

    def splinter(local_rng: random.Random, _index: int) -> Buf:
        m = dur(0.01 + local_rng.random() * 0.05, rate)
        snap = biquad(
            white(m, local_rng), rate, "bandpass", 700 + local_rng.random() * 3200, 3.2
        )
        return gain(mul(snap, env_perc(m, rate, 0.0006, 0.03, 3.0)), 0.35 + local_rng.random() * 0.6)

    debris = scatter(n, rate, rng, 22, splinter, spread=(0.0, 0.62))
    out = mix(pad(gain(body, 1.0), n), gain(boom, 0.7), gain(debris, 0.8))
    out = reflections(softclip(out, 1.5), rate, [(0.035, 0.2), (0.071, 0.12)])
    return normalize(pad(out, n), 0.9), rate


# --- the things you open ----------------------------------------------------
#
# THE OTHER VERB HAD NO SOUND OF ITS OWN. `crate-break` covers everything that
# shatters, and everything that OPENED was playing `bag-open` — the inventory
# panel's UI tick. So a car boot, a chest lid and the backpack all made the
# same noise, which quietly undid the whole point of the object vocabulary:
# the art, the verb and the prompt all say a chest is not a mailbox and is not
# a lorry, and then the loudest channel the game has said they are identical.
#
# Two recipes, because there are two weights of hinge out there. A LID is
# wood and small — the creak, then the knock of it hitting its stop. A PANEL
# is a car and a shrine — a low grind that has to be pushed, and metal
# arriving at the end of its travel. Both end on a settle, because what a
# player is listening for is the moment they can look inside.


def _settle_tick(rate: int):
    """One small thing shifting inside a container that just came open."""

    def make(local_rng: random.Random, _index: int) -> Buf:
        m = dur(0.008 + local_rng.random() * 0.03, rate)
        grain = biquad(
            white(m, local_rng), rate, "bandpass", 900 + local_rng.random() * 2600, 4.0
        )
        return gain(mul(grain, env_perc(m, rate, 0.0005, 0.02, 3.2)),
                    0.25 + local_rng.random() * 0.4)

    return make


def sfx_object_open(rng: random.Random, variant: int) -> tuple[Buf, int]:
    """A wooden lid on a hinge. Creak, stop, settle.

    Timed against the sheets that use it — box is 6 frames at 14 fps, chest is
    8 at 11 — so the knock lands with the lid's last frame rather than under it.
    The creak is a narrow resonant band climbing as the hinge turns, chopped by
    an LFO: a hinge that has been out in a wet forest for a year does not turn
    smoothly, it sticks and lets go, and that stutter is the whole character.
    """
    rate = SFX_RATE
    n = dur(0.62, rate)

    creak_n = dur(0.30, rate)
    base = 300.0 + rng.random() * 190.0
    creak = biquad(white(creak_n, rng), rate, "bandpass",
                   lambda t: base * (1.0 + 0.85 * t), 7.5)
    creak = mul(creak, env_from(creak_n, [(0.0, 0.0), (0.12, 1.0), (0.65, 0.6), (1.0, 0.0)]))
    creak = mul(creak, lfo(creak_n, rate, 24.0 + rng.random() * 16.0, 0.42, 0.62))

    knock_n = dur(0.16, rate)
    knock = mix(
        mul(tone(knock_n, lambda t: 200.0 - 70.0 * t, rate, "sine"),
            env_perc(knock_n, rate, 0.001, 0.09, 3.0)),
        mul(biquad(white(knock_n, rng), rate, "bandpass", 1500.0, 2.2),
            env_perc(knock_n, rate, 0.0005, 0.05, 3.4)),
    )

    out = at(pad(gain(creak, 0.85), n), gain(knock, 0.9), dur(0.28, rate))
    out = mix(out, gain(scatter(n, rate, rng, 5, _settle_tick(rate), spread=(0.32, 0.62)), 0.7))
    return normalize(reflections(out, rate, [(0.031, 0.17), (0.062, 0.09)]), 0.9), rate


def sfx_object_heavy(rng: random.Random, variant: int) -> tuple[Buf, int]:
    """A panel that has to be forced, and the stone that has to be pushed.

    The vehicles and the altar share it, and they share it on purpose: what
    those two have in common is that a person is moving something that does not
    want to move, which is a different sentence from a lid falling open. It is
    the longest of the three container sounds because the WAIT is the point —
    a car boot that opened instantly would cost the vehicles the one beat where
    the player has already committed and does not yet know what is in there.
    """
    rate = SFX_RATE
    n = dur(0.86, rate)

    # The grind: broadband, low, and it has to build rather than strike.
    grind_n = dur(0.52, rate)
    grind = biquad(brown(grind_n, rng), rate, "bandpass",
                   lambda t: 150.0 + 260.0 * t, 1.4)
    grind = mul(grind, env_from(grind_n, [(0.0, 0.0), (0.2, 0.75), (0.75, 1.0), (1.0, 0.25)]))
    grind = mul(grind, lfo(grind_n, rate, 11.0 + rng.random() * 7.0, 0.3, 0.72))

    # The seal letting go, a third of the way in.
    creak_n = dur(0.22, rate)
    creak = biquad(white(creak_n, rng), rate, "bandpass",
                   lambda t: 420.0 + 520.0 * t, 8.0)
    creak = mul(creak, env_perc(creak_n, rate, 0.02, 0.18, 1.8))

    # The stop: metal arriving at the end of its travel, with a ring on it.
    clank_n = dur(0.30, rate)
    clank = mix(
        mul(tone(clank_n, 128.0, rate, "sine"), env_perc(clank_n, rate, 0.001, 0.16, 2.8)),
        mul(tone(clank_n, 311.0, rate, "sine"), env_perc(clank_n, rate, 0.001, 0.11, 3.4)),
        mul(biquad(white(clank_n, rng), rate, "bandpass", 2400.0, 2.6),
            env_perc(clank_n, rate, 0.0004, 0.04, 4.0)),
    )

    out = pad(gain(grind, 0.9), n)
    out = at(out, gain(creak, 0.5), dur(0.14, rate))
    out = at(out, gain(clank, 0.85), dur(0.50, rate))
    out = mix(out, gain(scatter(n, rate, rng, 4, _settle_tick(rate), spread=(0.60, 0.88)), 0.6))
    out = reflections(softclip(out, 1.2), rate, [(0.041, 0.2), (0.083, 0.11)])
    return normalize(pad(out, n), 0.9), rate




def sfx_empty(rng: random.Random) -> tuple[Buf, int]:
    """NOTHING IN HERE — the sound of an opened container that did not pay.

    THIS IS THE ONE SOUND IN THE GAME WHOSE JOB IS TO REPORT AN ABSENCE, and it
    exists because an empty interaction and a FAILED one were audibly the same
    thing. A chest whose lid came up on nothing played the lid and then silence,
    which is exactly what a press the server dropped sounds like — so a player
    who found nothing could not tell whether they had found nothing or whether
    the game had ignored them.

    A hollow box knocked once, and dry air coming out of it. Low, short and
    QUIET: it has to be legible without being a punishment, because a run is
    made of these and a disappointment that stings every time teaches people to
    stop opening things.
    """
    rate = SFX_RATE
    n = dur(0.34, rate)

    # The box itself: a low resonance with nothing damping it, which is what
    # "hollow" is. Two partials rather than one — a single sine reads as a
    # tone rather than as a struck object.
    body_n = dur(0.26, rate)
    body = mix(
        mul(tone(body_n, lambda t: 132.0 - 26.0 * t, rate, "sine"),
            env_perc(body_n, rate, 0.002, 0.16, 2.6)),
        gain(mul(tone(body_n, 197.0, rate, "sine"),
                 env_perc(body_n, rate, 0.002, 0.1, 3.2)), 0.45),
    )

    # The air. A short filtered breath sliding down, so the box reads as having
    # had something in it once rather than as never having been sealed.
    air_n = dur(0.30, rate)
    air = biquad(pink(air_n, rng), rate, "bandpass",
                 lambda t: 900.0 - 480.0 * t, 1.1)
    air = mul(air, env_from(air_n, [(0.0, 0.0), (0.16, 1.0), (1.0, 0.0)]))

    out = pad(gain(body, 0.9), n)
    out = mix(out, gain(pad(air, n), 0.4))
    return normalize(reflections(out, rate, [(0.023, 0.16)]), 0.88), rate


# --- the upgrade machine ----------------------------------------------------
#
# THE CABINET NEEDED ITS OWN VOCABULARY AND THIS IS WHY. The pull was built out
# of `object-heavy` and `object-open` first, and it worked in the sense that
# sounds came out — which is exactly the failure mode the object vocabulary was
# written to stop. A car boot and a slot machine's lever are not the same
# event, and a machine assembled out of borrowed container noises reads as a
# container, whatever it looks like.
#
# Four sounds, and each one is a beat of the ceremony:
#
#   LEVER   a sprung arm going over centre. Ratchet, spring, and the clunk of
#           the mechanism catching at the bottom of its travel.
#   REEL    a detent landing. Three variants, and the client pitches the third
#           one up with the rarity — so the tier is audible a beat before the
#           canister exists.
#   CAN     a hollow metal tube hitting a steel tray. Deliberately not `drop`:
#           that one is loot landing on soil, and this has to ring.
#   JACKPOT the flourish, and it is only played for the top of the ladder. A
#           celebration on every pull is a celebration on none of them.


def sfx_lever(rng: random.Random) -> tuple[Buf, int]:
    """A sprung arm thrown over centre.

    Three parts and the order is the mechanism: the RATCHET as the arm is
    hauled down (hard clicks slowing as the spring loads), the SPRING itself (a
    short pitched ring bending as it stretches), and the CLUNK of the whole
    cabinet taking the stop. The clunk is low and has a body resonance on it,
    because what is being struck is a steel box with air in it — and that is
    the difference between a lever and a light switch.
    """
    rate = SFX_RATE
    n = dur(0.70, rate)

    def click(local_rng: random.Random, _index: int) -> Buf:
        m = dur(0.012, rate)
        tick = biquad(white(m, local_rng), rate, "bandpass",
                      1800 + local_rng.random() * 1400, 6.0)
        return gain(mul(tick, env_perc(m, rate, 0.0004, 0.008, 3.4)), 0.5)

    ratchet = scatter(dur(0.30, rate), rate, rng, 9, click, spread=(0.0, 0.85))

    spring_n = dur(0.26, rate)
    spring = mix(
        mul(tone(spring_n, lambda t: 620.0 - 210.0 * t, rate, "sine"),
            env_perc(spring_n, rate, 0.004, 0.2, 2.4)),
        gain(mul(tone(spring_n, lambda t: 1240.0 - 380.0 * t, rate, "sine"),
                 env_perc(spring_n, rate, 0.004, 0.12, 3.0)), 0.35),
    )

    clunk_n = dur(0.34, rate)
    clunk = mix(
        mul(tone(clunk_n, lambda t: 96.0 - 26.0 * t, rate, "sine"),
            env_perc(clunk_n, rate, 0.001, 0.2, 2.6)),
        mul(tone(clunk_n, 174.0, rate, "sine"), env_perc(clunk_n, rate, 0.001, 0.13, 3.2)),
        mul(biquad(white(clunk_n, rng), rate, "bandpass", 2100.0, 2.0),
            env_perc(clunk_n, rate, 0.0004, 0.045, 4.0)),
    )

    out = pad(gain(ratchet, 0.8), n)
    out = at(out, gain(spring, 0.5), dur(0.08, rate))
    out = at(out, gain(clunk, 0.95), dur(0.30, rate))
    out = reflections(softclip(out, 1.15), rate, [(0.026, 0.2), (0.055, 0.1)])
    return normalize(pad(out, n), 0.92), rate


def sfx_reel(rng: random.Random, variant: int) -> tuple[Buf, int]:
    """A reel dropping into its detent.

    Short, hard and PITCHED, because the client plays the third one at a rate
    that climbs with the rarity — a reel stop made of pure noise would take
    that channel away, and the pitch climbing under the third stop is most of
    what makes the wait worth having.
    """
    rate = SFX_RATE
    n = dur(0.20, rate)
    base = 340.0 + variant * 46.0 + rng.random() * 24.0

    body = mix(
        mul(tone(n, lambda t: base * (1.0 - 0.18 * t), rate, "sine"),
            env_perc(n, rate, 0.0008, 0.09, 3.2)),
        mul(tone(n, base * 2.51, rate, "sine"), env_perc(n, rate, 0.0006, 0.05, 3.8)),
    )
    edge = mul(biquad(white(n, rng), rate, "bandpass", 3200.0, 3.0),
               env_perc(n, rate, 0.0003, 0.022, 4.2))
    return normalize(mix(gain(body, 0.85), gain(edge, 0.5)), 0.9), rate


def sfx_can(rng: random.Random) -> tuple[Buf, int]:
    """A hollow tube landing in a steel tray, and rocking to a stop.

    It RINGS, which is the whole reason it is not `drop`. Loot landing on soil
    is a thud with grit in it; this is metal on metal inside a box, so it gets
    a long thin partial over the impact and two lighter taps behind it as the
    canister settles onto its side.
    """
    rate = SFX_RATE
    n = dur(0.56, rate)

    hit_n = dur(0.30, rate)
    hit = mix(
        mul(tone(hit_n, 208.0, rate, "sine"), env_perc(hit_n, rate, 0.0008, 0.1, 3.0)),
        mul(tone(hit_n, 1470.0, rate, "sine"), env_perc(hit_n, rate, 0.0006, 0.26, 2.2)),
        mul(biquad(white(hit_n, rng), rate, "bandpass", 2600.0, 2.4),
            env_perc(hit_n, rate, 0.0003, 0.03, 4.0)),
    )

    def rock(local_rng: random.Random, _index: int) -> Buf:
        m = dur(0.09, rate)
        tap = mix(
            mul(tone(m, 1180.0 + local_rng.random() * 320.0, rate, "sine"),
                env_perc(m, rate, 0.0006, 0.06, 2.8)),
            mul(biquad(white(m, local_rng), rate, "bandpass", 3000.0, 3.0),
                env_perc(m, rate, 0.0003, 0.015, 4.0)),
        )
        return gain(tap, 0.22 + local_rng.random() * 0.16)

    out = pad(gain(hit, 0.95), n)
    out = mix(out, scatter(n, rate, rng, 3, rock, spread=(0.34, 0.8)))
    return normalize(reflections(out, rate, [(0.019, 0.24), (0.041, 0.13)]), 0.92), rate


def sfx_jackpot(rng: random.Random) -> tuple[Buf, int]:
    """The flourish, and it is reserved for the top of the ladder.

    A rising four-note figure over a bed of small bright grains — the machine's
    bulbs all coming on at once. It is played ONLY behind an epic or a
    legendary, because a celebration that fires on every pull stops being one
    by the third shop; it is the audio half of the rule `pullGain` keeps on
    screen.
    """
    rate = SFX_RATE
    n = dur(1.30, rate)

    steps = (523.25, 659.25, 783.99, 1046.50)
    out = silence(n)
    for index, freq in enumerate(steps):
        note_n = dur(0.55, rate)
        note = mix(
            mul(tone(note_n, freq, rate, "sine"), env_perc(note_n, rate, 0.004, 0.34, 2.4)),
            gain(mul(tone(note_n, freq * 2.0, rate, "sine"),
                     env_perc(note_n, rate, 0.003, 0.18, 3.0)), 0.35),
            gain(mul(tone(note_n, freq * 3.01, rate, "sine"),
                     env_perc(note_n, rate, 0.002, 0.1, 3.6)), 0.14),
        )
        out = at(out, gain(note, 0.7 - index * 0.06), dur(0.09 * index, rate))

    def spark(local_rng: random.Random, _index: int) -> Buf:
        m = dur(0.07, rate)
        grain = mul(tone(m, 1800.0 + local_rng.random() * 2600.0, rate, "sine"),
                    env_perc(m, rate, 0.001, 0.045, 3.4))
        return gain(grain, 0.1 + local_rng.random() * 0.14)

    out = mix(out, scatter(n, rate, rng, 14, spark, spread=(0.05, 0.7)))
    return normalize(reverb(out, rate, room=0.7, damp=0.4, wet=0.16), 0.92), rate


# --- the knife --------------------------------------------------------------
#
# The blade's whole argument is that it is QUIET, and the mix has to say so
# before the noise radius in `weapons.py` ever does. A gunshot sits at the top
# of the ladder; both of these sit below a footstep's neighbours, so a player
# who knifes their way through a camp hears themselves working rather than
# announcing.


def sfx_knife_swing(rng: random.Random, variant: int) -> tuple[Buf, int]:
    """Steel cutting air. The whole sound is one narrow band arcing past you.

    Same shape as the zombie's swing and deliberately so — a swing is a swing
    — but an octave up, half as long and with none of the throat under it. A
    blade is edge and air; the arm carrying it is not the sound.

    The finisher is variant 2: slower sweep, lower centre, more weight. The
    caller picks it by index (see `playSfx('knife-swing', {variant})`), which
    is the same trick the rarity chimes use — one recipe, one shape, and the
    step in the chain chooses which of them you hear.
    """
    rate = SFX_RATE
    # The cut is the slow one. Two quick slashes, then something with a body.
    heavy = variant >= 2
    n = dur(0.26 if heavy else 0.17, rate)
    top = 7800.0 if heavy else 9600.0
    base = 1400.0 if heavy else 2100.0

    def arc(t: float) -> float:
        # Peaks early: the fastest part of a swing is the start of it.
        return base + (top - base) * math.sin(min(1.0, t * 1.35) * math.pi) ** 0.6

    air = biquad(white(n, rng), rate, "bandpass", arc, 3.4 if heavy else 4.2)
    air = mul(air, env_from(n, [(0.0, 0.0), (0.12, 1.0), (0.4, 0.45), (1.0, 0.0)]))

    # A second, thinner edge just behind it. One band alone is a hiss; two
    # passing a beat apart is a thing with an edge going through the air.
    edge = biquad(white(n, rng), rate, "bandpass", lambda t: 4200 + 5200 * t, 5.0)
    edge = mul(edge, env_from(n, [(0.0, 0.0), (0.22, 0.7), (0.5, 0.14), (1.0, 0.0)]))

    layers = [gain(air, 1.0), gain(edge, 0.5)]
    if heavy:
        # The cut alone gets a low push under it — the weight the two slashes
        # do not have, which is what makes the third beat feel like the end
        # of the chain rather than a third of the same thing.
        body = mul(
            tone(n, lambda t: 190.0 - 90.0 * t, rate, "sine"),
            env_perc(n, rate, 0.004, 0.13, 2.6),
        )
        layers.append(gain(body, 0.34))

    return normalize(softclip(mix(*layers), 1.4), 0.8), rate


def sfx_knife_hit(rng: random.Random, variant: int) -> tuple[Buf, int]:
    """The blade going in. Wetter and shorter than a bullet, with no crack.

    `zombie-hit` opens with a dry slap because a round arrives before it does
    anything. A knife has no arrival — it is already in contact — so this
    starts on the squelch and the only bright layer is the edge sliding out
    the far side.
    """
    rate = SFX_RATE
    n = dur(0.26, rate)
    squelch = biquad(white(dur(0.14, rate), rng), rate, "bandpass", lambda t: 780 - 480 * t, 2.6)
    squelch = mul(squelch, env_perc(len(squelch), rate, 0.001, 0.12, 2.4))
    # The withdraw: a thin band a beat later, brighter than the entry.
    draw = biquad(white(dur(0.09, rate), rng), rate, "bandpass", lambda t: 2400 + 1600 * t, 4.0)
    draw = mul(draw, env_perc(len(draw), rate, 0.001, 0.07, 2.8))
    thud = mul(
        tone(n, lambda t: 96.0 - 42.0 * t, rate, "sine"), env_perc(n, rate, 0.002, 0.1, 2.8)
    )
    out = mix(
        pad(gain(squelch, 1.0), n),
        at(silence(n), gain(draw, 0.4), int(0.05 * rate)),
        gain(thud, 0.5),
    )
    return normalize(softclip(out, 1.6), 0.72), rate


def sfx_drop(rng: random.Random) -> tuple[Buf, int]:
    """Something leaving the bag and hitting dirt."""
    rate = SFX_RATE
    n = dur(0.3, rate)
    thud = biquad(white(dur(0.1, rate), rng), rate, "lowpass", lambda t: 900 - 620 * t)
    thud = mul(thud, env_perc(len(thud), rate, 0.002, 0.09, 2.6))
    low = mul(tone(n, lambda t: 96.0 - 44.0 * t, rate, "sine"), env_perc(n, rate, 0.003, 0.12, 2.8))
    return normalize(softclip(mix(pad(gain(thud, 0.9), n), gain(low, 0.6)), 1.3), 0.6), rate


# ===========================================================================
# BUILD
# ===========================================================================

#: Absolute loudness the reference level lands on. Everything in `CATALOG` is
#: an offset from this, so moving it moves the whole game at once.
REFERENCE_LUFS = -15.0

#: name -> (recipe, variants, level_db, bus, loop)
#:
#: `level_db` IS THE MIX, and it is a measured quantity rather than a guess.
#: The generator renders the sound, measures what it actually came out at
#: (`loudness_lufs`), and computes the manifest gain needed to land it here —
#: so 0 dB and -18 dB really are eighteen decibels apart to the ear, and the
#: same number on two different sounds means the same loudness. That is what
#: makes 50 on one of the game's volume sliders match 50 on another.
#:
#: The ladder is therefore the ONLY artistic decision left in the mix, and it
#: reads as one: a gunshot at the top, footsteps eighteen down, beds far below
#: everything because they never stop.
#:
#: `bus` is the row in the player's options panel, so the grouping is a
#: PLAYER-FACING taxonomy and not an engineering one:
#:
#:   ui       the interface answering: a refusal, the bag
#:   ambient  the loops that are always there, plus the corridor drone
#:   sfx      GUNS AND ZOMBIES ONLY — the loud, violent half. Deliberately
#:            narrow, because somebody who wants combat quieter must not lose
#:            their own footsteps to do it.
#:   misc     everything else that happens: steps, loot, crates, the lamp, the
#:            transitions
CATALOG: dict[str, tuple[object, int, float, str, bool]] = {
    # interface — see the banner above: no hover, no click. A refusal and a bag.
    # Low: these play when nothing else is happening, which makes them feel
    # louder than their numbers.
    "ui-error": (ui_error, 1, -12.0, "ui", False),
    "bag-open": (ui_bag_open, 1, -14.0, "ui", False),
    "bag-close": (ui_bag_close, 1, -15.0, "ui", False),
    "ready": (sfx_ready, 1, -13.0, "ui", False),
    "unready": (sfx_unready, 1, -14.0, "ui", False),
    # ambience — the loops, and the one drone that behaves like one.
    # FAR down the ladder, and that is not timidity: a bed never stops, so it
    # accumulates over a whole run in a way a one-shot never does. A bed at
    # footstep level is exhausting inside two minutes.
    "fire": (bed_fire, 1, -22.0, "ambient", True),
    "wind": (bed_wind, 1, -25.0, "ambient", True),
    "night": (bed_night, 1, -27.0, "ambient", True),
    "rain": (bed_rain, 1, -23.0, "ambient", True),
    "heartbeat": (bed_heartbeat, 1, -20.0, "ambient", True),
    "void": (sfx_void, 1, -14.0, "ambient", False),
    # guns and zombies — the top of the ladder
    "shot": (sfx_shot, 3, 0.0, "sfx", False),
    # The shotgun gets its own recipe rather than a playback rate. See the
    # note on `sfx_shotgun`: the ONE thing pitch cannot fake is a transient
    # that stays short while everything under it gets long.
    "shotgun": (sfx_shotgun, 2, 0.0, "sfx", False),
    "hurt": (sfx_hurt, 3, -3.0, "sfx", False),
    "zombie-idle": (sfx_zombie_idle, 3, -9.0, "sfx", False),
    "zombie-alert": (sfx_zombie_alert, 2, -5.0, "sfx", False),
    "zombie-attack": (sfx_zombie_attack, 3, -4.0, "sfx", False),
    "zombie-hit": (sfx_zombie_hit, 3, -6.0, "sfx", False),
    "zombie-death": (sfx_zombie_death, 3, -5.0, "sfx", False),
    # The knife, and its place on the ladder IS the weapon. Three variants,
    # because the caller forces one per combo step: 0 and 1 are the slashes,
    # 2 is the cut. Both rows sit far below the gun — a blade that read as
    # loud as a Glock would take the reason to carry it away.
    "knife-swing": (sfx_knife_swing, 3, -14.0, "sfx", False),
    "knife-hit": (sfx_knife_hit, 3, -9.0, "sfx", False),
    # everything else that happens
    "step-soft": (sfx_step_soft, 4, -18.0, "misc", False),
    "step-litter": (sfx_step_litter, 4, -18.0, "misc", False),
    "lantern-on": (sfx_lantern_on, 1, -15.0, "misc", False),
    "lantern-off": (sfx_lantern_off, 1, -15.0, "misc", False),
    "lantern-flicker": (sfx_lantern_flicker, 1, -17.0, "misc", False),
    "kindle": (sfx_kindle, 1, -4.0, "misc", False),
    "summon": (sfx_summon, 1, -16.0, "misc", False),
    "arrive": (sfx_arrive, 1, -3.0, "misc", False),
    # NEAR THE TOP OF `misc` ON PURPOSE, and above `arrive`. It repeats every
    # 0.75s for a whole pickup, which normally argues for going quiet — but
    # this is the one sound in the game whose job is to be the reason the
    # player cannot think about anything else, and a siren the horde can
    # clearly hear while the party can barely tell is the wrong way round. It
    # is in `misc` rather than `sfx` because somebody who turned combat down
    # must not be able to turn the alarm off with it.
    "siren": (sfx_siren, 1, -2.0, "misc", False),
    "dread": (sfx_dread, 3, -11.0, "misc", False),
    "loot": (sfx_loot, 1, -11.0, "misc", False),
    "rarity": (sfx_rarity, 5, -9.0, "misc", False),
    "coin": (sfx_coin, 1, -12.0, "misc", False),
    "crate-break": (sfx_crate_break, 3, -4.0, "misc", False),
    # Quieter than the smash by design: the whole reason to walk to a chest
    # rather than shoot a barrel is that opening one does not announce you.
    "object-open": (sfx_object_open, 3, -9.0, "misc", False),
    "object-heavy": (sfx_object_heavy, 3, -7.0, "misc", False),
    "drop": (sfx_drop, 1, -13.0, "misc", False),
    # WELL DOWN THE LADDER, and deliberately. It reports that nothing
    # happened, and a disappointment that is as loud as a find teaches
    # people to stop opening things. Quiet enough to be information.
    "empty": (sfx_empty, 1, -16.0, "misc", False),
    # THE UPGRADE MACHINE. `misc`, because it is neither combat nor the
    # interface, and it sits a step ABOVE the containers: the cabinet is the
    # loudest thing in a zone with no threat in it, and the whole ceremony is
    # supposed to make a party at the other end of the glade look over.
    "lever": (sfx_lever, 1, -6.0, "misc", False),
    "reel": (sfx_reel, 3, -10.0, "misc", False),
    "can": (sfx_can, 1, -9.0, "misc", False),
    # The one sound in the game that is deliberately rare: epic and legendary
    # only. Loud enough to be an event, short enough not to sit on top of the
    # rarity chime it plays behind.
    "jackpot": (sfx_jackpot, 1, -5.0, "misc", False),
}

#: Base for every per-sound seed. Changing it reshuffles every variant in the
#: game at once, which is occasionally what you want and never an accident.
SEED_SALT = 0x5A4D


def _seed_for(name: str, variant: int) -> int:
    """Stable per-(sound, variant) seed. Not `hash()` — that is salted per run."""
    acc = SEED_SALT
    for char in name:
        acc = (acc * 131 + ord(char)) & 0xFFFFFFFF
    return (acc * 31 + variant * 7919) & 0xFFFFFFFF


#: Peak every file is written at. Uniform, so the samples always use the full
#: word and the loudness correction below has a known amount of room above it.
WRITE_PEAK = 0.97

#: A computed gain is never allowed to push a file past this at playback. The
#: clamp is reported, because hitting it means the ladder is asking for a
#: loudness that sound cannot reach without clipping — which is a signal to fix
#: the recipe, not to quietly accept a wrong level.
PLAY_CEILING = 0.99


def build(only: set[str] | None = None) -> Path:
    out_dir = PROCESSED_DIR / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, dict] = {}
    total_bytes = 0
    clamped: list[str] = []
    unmeasured: list[str] = []
    # Measured loudness per file, kept so `--only` can rewrite the manifest in
    # full without re-rendering everything. It is COMMITTED OUTPUT, not a
    # scratch cache: the manifest's gains are derived from it, so a checkout
    # without it cannot produce a correct manifest from a partial run.
    cache_path = out_dir / "loudness.json"
    try:
        measured: dict[str, float] = json.loads(cache_path.read_text())
    except (OSError, ValueError):
        measured = {}

    for name, (recipe, variants, level, bus, loop) in CATALOG.items():
        entry: dict = {"files": [], "bus": bus}
        if loop:
            entry["loop"] = True

        levels: list[float] = []
        for variant in range(variants):
            filename = f"{name}.wav" if variants == 1 else f"{name}-{variant}.wav"
            entry["files"].append(filename)

            if only is not None and name not in only:
                if filename in measured:
                    levels.append(measured[filename])
                continue

            rng = random.Random(_seed_for(name, variant))
            samples, rate = (
                recipe(rng) if variants == 1 else recipe(rng, variant)  # type: ignore[operator]
            )
            # Every one-shot gets its offset removed and its ends taken to
            # zero regardless of what the recipe did. One sample of DC at an
            # edge is an audible tick, and it is not worth auditing thirty
            # recipes for it.
            #
            # Loops are exempt from BOTH. A filter with memory has a settling
            # transient at the head, which is exactly the sample `loopify` just
            # crossfaded to meet the tail — running it here would re-open the
            # seam the bed exists to hide. Beds are checked for offset instead.
            if not loop:
                samples = fade(dc_block(samples, rate), rate, 0.002, 0.006)
            # Uniform peak, so what the recipe happened to normalize to stops
            # mattering — loudness is set by the manifest gain, not by the file.
            samples = normalize(samples, WRITE_PEAK)

            lufs = loudness_lufs(samples, rate)
            measured[filename] = lufs
            levels.append(lufs)

            written = save_wav(out_dir / filename, samples, rate)
            total_bytes += written
            print(
                f"  {filename:24s} {len(samples) / rate:5.2f}s "
                f"{written // 1024:4d} KB  {lufs:7.1f} LUFS"
            )

        # One gain per SOUND, from the mean of its variants — never per file.
        # Variants are meant to differ slightly; levelling each one individually
        # would iron out exactly the variation they exist to provide.
        if levels:
            mean = sum(levels) / len(levels)
            wanted = 10.0 ** ((REFERENCE_LUFS + level - mean) / 20.0)
            ceiling = PLAY_CEILING / WRITE_PEAK
            if wanted > ceiling:
                clamped.append(f"{name} (wanted {20 * math.log10(wanted / ceiling):+.1f} dB more)")
                wanted = ceiling
            entry["gain"] = round(wanted, 4)
        else:
            # No measurement and not re-rendered: `--only` on a tree with no
            # loudness.json. Unity is the only safe answer and it is the WRONG
            # level, so say so loudly rather than shipping a silent mix bug.
            unmeasured.append(name)
            entry["gain"] = 1.0

        manifest[name] = entry

    (out_dir / "manifest.json").write_text(json.dumps({"sounds": manifest}, indent=2) + "\n")
    cache_path.write_text(json.dumps(measured, indent=2, sort_keys=True) + "\n")

    print(f"wrote {out_dir}: {len(CATALOG)} sounds, {total_bytes // 1024} KB total")
    if clamped:
        print("  !! level unreachable without clipping: " + ", ".join(clamped))
    if unmeasured:
        print(
            "  !! NO LOUDNESS MEASUREMENT for "
            + ", ".join(unmeasured)
            + " — their gains are unity and WRONG. Run without --only."
        )
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--only",
        default="",
        help="comma-separated sound names to re-render; the manifest is always rewritten in full",
    )
    args = ap.parse_args()
    only = {part.strip() for part in args.only.split(",") if part.strip()} or None
    if only:
        unknown = only - CATALOG.keys()
        if unknown:
            ap.error(f"unknown sound(s): {', '.join(sorted(unknown))}")
    build(only)


if __name__ == "__main__":
    main()
