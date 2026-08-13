/**
 * The campfire: the lobby's canvas, and the title screen's backdrop.
 *
 * This is a scene, not a game. Nothing here is authoritative, nothing is
 * predicted, no input is read — the party standing around the fire is the
 * roster the server broadcast, drawn. That is exactly why it can afford to be
 * expensive-looking: it costs a handful of gradients and a couple of hundred
 * particles, and it is the first thing anybody sees.
 *
 * Everything is authored in LOGICAL pixels (the game's own scale, 16 px to a
 * tile) and blitted through an integer `zoom`, so the art stays on its pixel
 * grid at any window size. The one exception is text: names are drawn in
 * SCREEN space after the world pass, because Departure Mono is only crisp at
 * multiples of 11 screen px and would shimmer if it were scaled with the rest.
 *
 * Lifecycle is explicit — `start()` / `dispose()`, same contract as `Game`.
 */

import { clamp01, lerp } from '../lib/math';
import { get2d } from '../lib/canvas';
import { facingFromAim, frameIndex, SpriteBook } from '../render/sprites';
import { HUD_GRID, hudFont, whenFontsReady } from '../theme/fonts';
import { floorColor, hasFloorSpeck, palette } from '../theme/palette';

const TAU = Math.PI * 2;
/** Sprite sheet every seated player is drawn from. */
const PLAYER_SHEET = 'player';
/** Tile size of the ground dither. Matches the arena's floor so it reads as the same world. */
const TILE = 16;

/** Seat ring, in logical px. Elliptical: a circle reads as a flat disc from this angle. */
const RING_RX = 54;
const RING_RY = 31;
/** How fast a seat slides to its new angle when the party grows. */
const RESEAT_RATE = 3.2;

/** Seconds a player spends materialising, and dissolving. */
const SUMMON_TIME = 1.05;
const LEAVE_TIME = 0.45;
/** When in the summon the body starts to appear, and when it has fully landed. */
const BODY_FADE_IN = 0.42;
const BODY_LANDED = 0.72;

/** Embers per second thrown by the fire. */
const EMBER_RATE = 16;

export interface LobbyMember {
  id: string;
  name: string;
  color: string;
  isLocal: boolean;
  isHost: boolean;
}

type SeatPhase = 'summoning' | 'seated' | 'leaving';

interface Seat {
  id: string;
  name: string;
  color: string;
  isLocal: boolean;
  isHost: boolean;
  /** Current and desired position on the ring, in radians. */
  angle: number;
  targetAngle: number;
  phase: SeatPhase;
  /** Seconds spent in the current phase. */
  t: number;
  /** Per-seat offset so idle bobbing is not synchronised across the party. */
  bobPhase: number;
  animTime: number;
}

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  age: number;
  life: number;
  size: number;
  color: string;
  /** Upward drag / gravity, logical px per second squared. */
  gy: number;
  /**
   * Summon motes home on a point instead of drifting: with a target set,
   * position is an eased interpolation and the velocity fields are ignored.
   */
  tx?: number;
  ty?: number;
  sx?: number;
  sy?: number;
}

interface Ring {
  x: number;
  y: number;
  age: number;
  life: number;
  maxRadius: number;
  color: string;
}

export class LobbyScene {
  private readonly canvas: HTMLCanvasElement;
  private readonly ctx: CanvasRenderingContext2D;
  private readonly sprites: SpriteBook;

  private readonly seats: Seat[] = [];
  private readonly particles: Particle[] = [];
  private readonly rings: Ring[] = [];

  private resizeObserver: ResizeObserver | null = null;
  private rafId: number | null = null;
  private started = false;
  private disposed = false;
  private resizeDirty = true;

  private zoom = 3;
  private dpr = 1;
  /** Scene origin (the fire) in device px. */
  private originX = 0;
  private originY = 0;
  private time = 0;
  private lastFrame = 0;
  private emberDebt = 0;
  /** 0..1 flame brightness, driven by layered sines. Read by every lit thing. */
  private flicker = 1;

  constructor(canvas: HTMLCanvasElement, sprites: SpriteBook = new SpriteBook()) {
    this.canvas = canvas;
    this.ctx = get2d(canvas, 'lobby-scene');
    this.sprites = sprites;
  }

  async start(): Promise<void> {
    if (this.started || this.disposed) return;
    this.started = true;

    // The webfont too: names drawn in the fallback face and then swapped is the
    // one flicker in this scene that is not on purpose.
    await Promise.all([this.sprites.load([PLAYER_SHEET]), whenFontsReady()]);
    if (this.disposed) return;

    // Reading clientWidth every frame forces a layout; only resize on change.
    this.resizeObserver = new ResizeObserver(() => {
      this.resizeDirty = true;
    });
    this.resizeObserver.observe(this.canvas);

    this.lastFrame = performance.now();
    this.rafId = requestAnimationFrame(this.frame);
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    if (this.rafId !== null) cancelAnimationFrame(this.rafId);
    this.rafId = null;
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    this.seats.length = 0;
    this.particles.length = 0;
    this.rings.length = 0;
  }

  /**
   * Reconcile the drawn party with the roster.
   *
   * Arrivals get summoned rather than appearing: a player who blinks into
   * existence reads as a rendering bug, and the whole point of the lobby is to
   * make somebody joining feel like an event. Departures dissolve for the same
   * reason. The local player always takes the front seat, so "which one is me"
   * is never a question.
   */
  setMembers(members: readonly LobbyMember[]): void {
    const ordered = [...members].sort(
      (a, b) => Number(b.isLocal) - Number(a.isLocal),
    );
    const live = new Set(ordered.map((m) => m.id));

    for (const seat of this.seats) {
      if (seat.phase !== 'leaving' && !live.has(seat.id)) {
        seat.phase = 'leaving';
        seat.t = 0;
        this.spawnDeparture(seat);
      }
    }

    ordered.forEach((member, index) => {
      const angle = seatAngle(index, ordered.length);
      const existing = this.seats.find((s) => s.id === member.id && s.phase !== 'leaving');
      if (existing) {
        existing.name = member.name;
        existing.color = member.color;
        existing.isHost = member.isHost;
        existing.targetAngle = nearestTurn(existing.angle, angle);
        return;
      }
      const seat: Seat = {
        id: member.id,
        name: member.name,
        color: member.color,
        isLocal: member.isLocal,
        isHost: member.isHost,
        angle,
        targetAngle: angle,
        phase: 'summoning',
        t: 0,
        bobPhase: Math.random() * TAU,
        animTime: Math.random(),
      };
      this.seats.push(seat);
      this.spawnSummon(seat);
    });
  }

  // --- vfx -----------------------------------------------------------------
  /** A column of motes falling out of the dark onto an empty seat. */
  private spawnSummon(seat: Seat): void {
    const { x, y } = seatPosition(seat.angle);
    const tone = palette().summon;
    for (let i = 0; i < 34; i++) {
      const spread = (Math.random() * 2 - 1) * 11;
      const startY = y - 90 - Math.random() * 150;
      this.particles.push({
        x: x + spread,
        y: startY,
        sx: x + spread,
        sy: startY,
        tx: x + spread * 0.15,
        ty: y - Math.random() * 12,
        vx: 0,
        vy: 0,
        gy: 0,
        age: -Math.random() * 0.35,
        life: SUMMON_TIME * (0.6 + Math.random() * 0.3),
        size: Math.random() < 0.25 ? 2 : 1,
        color: Math.random() < 0.3 ? tone.core : tone.spark,
      });
    }
  }

  /** The landing: a flat shockwave and a burst of sparks kicked off the ground. */
  private spawnLanding(seat: Seat): void {
    const { x, y } = seatPosition(seat.angle);
    const tone = palette().summon;
    this.rings.push({ x, y, age: 0, life: 0.5, maxRadius: 26, color: tone.core });
    this.rings.push({ x, y, age: -0.08, life: 0.62, maxRadius: 38, color: seat.color });
    for (let i = 0; i < 16; i++) {
      const angle = Math.random() * TAU;
      const speed = 24 + Math.random() * 46;
      this.particles.push({
        x,
        y,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed * 0.45 - 14,
        gy: 90,
        age: 0,
        life: 0.35 + Math.random() * 0.4,
        size: 1,
        color: i % 3 === 0 ? seat.color : tone.spark,
      });
    }
  }

  private spawnDeparture(seat: Seat): void {
    const { x, y } = seatPosition(seat.angle);
    for (let i = 0; i < 18; i++) {
      this.particles.push({
        x: x + (Math.random() * 2 - 1) * 5,
        y: y - Math.random() * 14,
        vx: (Math.random() * 2 - 1) * 12,
        vy: -18 - Math.random() * 26,
        gy: -6,
        age: 0,
        life: 0.45 + Math.random() * 0.35,
        size: 1,
        color: seat.color,
      });
    }
  }

  private spawnEmbers(dt: number): void {
    this.emberDebt += dt * EMBER_RATE * (0.6 + this.flicker * 0.7);
    const tones = palette().fire.embers;
    while (this.emberDebt >= 1) {
      this.emberDebt -= 1;
      this.particles.push({
        x: (Math.random() * 2 - 1) * 5,
        y: -4 - Math.random() * 6,
        vx: (Math.random() * 2 - 1) * 9,
        vy: -22 - Math.random() * 26,
        // Embers slow as they cool, so gravity is a gentle brake, not a fall.
        gy: 7,
        age: 0,
        life: 1 + Math.random() * 1.6,
        size: Math.random() < 0.18 ? 2 : 1,
        color: tones[Math.floor(Math.random() * tones.length)],
      });
    }
  }

  // --- loop ----------------------------------------------------------------
  private frame = (now: number): void => {
    if (this.disposed) return;
    const dt = Math.min(0.1, (now - this.lastFrame) / 1000);
    this.lastFrame = now;
    this.time += dt;

    if (this.resizeDirty) {
      this.resize();
      this.resizeDirty = false;
    }

    this.update(dt);
    this.draw();

    this.rafId = requestAnimationFrame(this.frame);
  };

  private resize(): void {
    const { canvas } = this;
    this.dpr = Math.min(2, window.devicePixelRatio || 1);
    const width = Math.max(1, Math.round(canvas.clientWidth * this.dpr));
    const height = Math.max(1, Math.round(canvas.clientHeight * this.dpr));
    if (canvas.width !== width) canvas.width = width;
    if (canvas.height !== height) canvas.height = height;
    // Integer zoom only: a fractional one puts the sprite grid between screen
    // pixels and the whole scene goes soft.
    this.zoom = Math.max(2, Math.floor(Math.min(width / 300, height / 210)));
    this.originX = Math.round(width / 2);
    // The fire sits above centre so the front row has room to stand.
    this.originY = Math.round(height * 0.46);
    this.ctx.imageSmoothingEnabled = false;
  }

  private update(dt: number): void {
    // Three sines with no common period: the fire never repeats a beat, which
    // is the whole difference between "burning" and "animated".
    const t = this.time;
    this.flicker = clamp01(
      0.72 +
        Math.sin(t * 7.3) * 0.11 +
        Math.sin(t * 13.1 + 1.7) * 0.08 +
        Math.sin(t * 2.9 + 0.4) * 0.09,
    );

    this.spawnEmbers(dt);

    for (const seat of this.seats) {
      seat.t += dt;
      seat.animTime += dt;
      seat.angle = lerp(seat.angle, seat.targetAngle, 1 - Math.exp(-RESEAT_RATE * dt));
      if (seat.phase === 'summoning') {
        // The shockwave fires the moment the body finishes resolving.
        if (seat.t >= BODY_LANDED * SUMMON_TIME && seat.t - dt < BODY_LANDED * SUMMON_TIME) {
          this.spawnLanding(seat);
        }
        if (seat.t >= SUMMON_TIME) {
          seat.phase = 'seated';
          seat.t = 0;
        }
      }
    }
    // Departed seats leave the array only once their dissolve has played out.
    for (let i = this.seats.length - 1; i >= 0; i--) {
      if (this.seats[i].phase === 'leaving' && this.seats[i].t >= LEAVE_TIME) {
        this.seats.splice(i, 1);
      }
    }

    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i];
      p.age += dt;
      if (p.age >= p.life) {
        this.particles.splice(i, 1);
        continue;
      }
      if (p.age < 0) continue;
      if (p.tx !== undefined && p.ty !== undefined) {
        // Ease-in: motes drift, then drop. A linear fall reads as rain.
        const k = clamp01(p.age / p.life) ** 2.1;
        p.x = lerp(p.sx ?? p.x, p.tx, k);
        p.y = lerp(p.sy ?? p.y, p.ty, k);
        continue;
      }
      p.vy += p.gy * dt;
      p.x += p.vx * dt;
      p.y += p.vy * dt;
    }

    for (let i = this.rings.length - 1; i >= 0; i--) {
      this.rings[i].age += dt;
      if (this.rings[i].age >= this.rings[i].life) this.rings.splice(i, 1);
    }
  }

  // --- drawing -------------------------------------------------------------
  private draw(): void {
    const { ctx, canvas } = this;
    const tone = palette();

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = tone.surface;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.save();
    ctx.translate(this.originX, this.originY);
    ctx.scale(this.zoom, this.zoom);

    const halfW = this.originX / this.zoom;
    const halfH = this.originY / this.zoom;
    const bottom = (canvas.height - this.originY) / this.zoom;
    const right = (canvas.width - this.originX) / this.zoom;

    this.drawGround(-halfW, -halfH, right, bottom);
    this.drawNight(Math.max(halfW, right), Math.max(halfH, bottom));
    this.drawFirelight();
    this.drawBeams(halfH);
    this.drawFire();
    this.drawSeats();
    this.drawParticles();
    this.drawRings();

    ctx.restore();
    this.drawLabels();
  }

  /** The same dithered forest floor the arena paints, so this is the same world. */
  private drawGround(left: number, top: number, right: number, bottom: number): void {
    const { ctx } = this;
    const tone = palette();
    const x0 = Math.floor(left / TILE);
    const x1 = Math.ceil(right / TILE);
    const y0 = Math.floor(top / TILE);
    const y1 = Math.ceil(bottom / TILE);

    for (let ty = y0; ty <= y1; ty++) {
      for (let tx = x0; tx <= x1; tx++) {
        ctx.fillStyle = floorColor(tx + 64, ty + 64);
        ctx.fillRect(tx * TILE, ty * TILE, TILE, TILE);
        if (hasFloorSpeck(tx + 64, ty + 64)) {
          ctx.fillStyle = tone.tiles.floorSpeck;
          ctx.fillRect(tx * TILE + 5, ty * TILE + 9, 2, 1);
        }
      }
    }
  }

  /** Everything past the fire's reach is night, not floor. */
  private drawNight(halfW: number, halfH: number): void {
    const { ctx } = this;
    const tone = palette();
    const reach = Math.hypot(halfW, halfH);
    const gradient = ctx.createRadialGradient(0, 0, RING_RX * 0.5, 0, 0, reach);
    gradient.addColorStop(0, 'rgb(0 0 0 / 0)');
    gradient.addColorStop(0.34, `rgb(${tone.night.shadow.join(' ')} / 0.55)`);
    gradient.addColorStop(0.72, `rgb(${tone.night.shadow.join(' ')} / 0.94)`);
    gradient.addColorStop(1, tone.surface);
    ctx.fillStyle = gradient;
    ctx.fillRect(-halfW - TILE, -halfH - TILE, (halfW + TILE) * 2, (halfH + TILE) * 2);
  }

  /** The warm pool the fire actually throws. Breathes with the flicker. */
  private drawFirelight(): void {
    const { ctx } = this;
    const glow = palette().fire.glow.join(' ');
    const radius = 96 + this.flicker * 26;

    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    const gradient = ctx.createRadialGradient(0, -4, 2, 0, -4, radius);
    gradient.addColorStop(0, `rgb(${glow} / ${(0.5 * this.flicker).toFixed(3)})`);
    gradient.addColorStop(0.35, `rgb(${glow} / ${(0.19 * this.flicker).toFixed(3)})`);
    gradient.addColorStop(1, `rgb(${glow} / 0)`);
    ctx.fillStyle = gradient;
    ctx.fillRect(-radius, -radius - 4, radius * 2, radius * 2);
    ctx.restore();
  }

  private drawFire(): void {
    const { ctx } = this;
    const fire = palette().fire;
    const t = this.time;

    // Stones, then logs. Both are lit from the flame above, so their top edge
    // gets the warm tone and the rest stays in shadow.
    ctx.fillStyle = fire.stone;
    for (let i = 0; i < 7; i++) {
      const angle = (i / 7) * TAU + 0.3;
      ctx.fillRect(Math.round(Math.cos(angle) * 13) - 1, Math.round(Math.sin(angle) * 7) + 1, 3, 2);
    }

    const logs: [number, number, number][] = [
      [-7, 0, 0.22],
      [-6, 2, -0.3],
      [-1, 3, 1.35],
    ];
    for (const [x, y, angle] of logs) {
      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(angle);
      ctx.fillStyle = fire.log;
      ctx.fillRect(0, 0, 14, 3);
      ctx.fillStyle = fire.logLit;
      ctx.fillRect(0, 0, 14, 1);
      ctx.restore();
    }

    // Three nested tongues. Each one is narrower, shorter-lived and hotter than
    // the one behind it, and they wobble at unrelated rates — that mismatch is
    // what stops the flame reading as a single looping sprite.
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    const tongues: [string, number, number, number, number][] = [
      [fire.outer, 9, 22, 5.1, 0.55],
      [fire.mid, 6, 16, 7.7, 0.75],
      [fire.core, 3, 9, 11.3, 0.95],
    ];
    for (const [color, width, height, rate, alpha] of tongues) {
      const sway = Math.sin(t * rate) * 1.6 + Math.sin(t * rate * 0.37 + 2) * 1.1;
      const stretch = height * (0.78 + this.flicker * 0.34);
      ctx.globalAlpha = alpha * (0.7 + this.flicker * 0.3);
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.moveTo(-width / 2, 1);
      ctx.quadraticCurveTo(-width * 0.62 + sway * 0.4, -stretch * 0.55, sway, -stretch);
      ctx.quadraticCurveTo(width * 0.62 + sway * 0.4, -stretch * 0.55, width / 2, 1);
      ctx.closePath();
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    ctx.restore();
  }

  /** The summoning column, drawn behind the bodies it is delivering. */
  private drawBeams(halfH: number): void {
    const { ctx } = this;
    const beam = palette().summon.beam.join(' ');

    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    for (const seat of this.seats) {
      if (seat.phase !== 'summoning') continue;
      const progress = clamp01(seat.t / SUMMON_TIME);
      const { x, y } = seatPosition(seat.angle);
      const strength = Math.sin(Math.PI * progress) ** 0.7;
      const width = 3 + strength * 9;
      const top = -halfH - TILE;

      const gradient = ctx.createLinearGradient(0, top, 0, y);
      gradient.addColorStop(0, `rgb(${beam} / 0)`);
      gradient.addColorStop(0.55, `rgb(${beam} / ${(0.16 * strength).toFixed(3)})`);
      gradient.addColorStop(1, `rgb(${beam} / ${(0.42 * strength).toFixed(3)})`);
      ctx.fillStyle = gradient;
      ctx.fillRect(x - width / 2, top, width, y - top);
    }
    ctx.restore();
  }

  /**
   * The party, painted back to front.
   *
   * Depth sorting is by seat Y and nothing else: the ring is shallow enough
   * that overlap only ever happens between neighbours, and a full sort of a
   * handful of seats is cheaper than any structure that would avoid it.
   */
  private drawSeats(): void {
    const { ctx } = this;
    const sheet = this.sprites.get(PLAYER_SHEET);
    if (!sheet) return;

    const ordered = [...this.seats].sort(
      (a, b) => seatPosition(a.angle).y - seatPosition(b.angle).y,
    );
    const tone = palette();

    for (const seat of ordered) {
      const { x, y } = seatPosition(seat.angle);
      const alpha = this.seatAlpha(seat);
      if (alpha <= 0.01) continue;

      const bob = Math.round(Math.sin(this.time * 1.7 + seat.bobPhase) * 1);
      const facing = facingFromAim(-Math.cos(seat.angle) * RING_RX, -Math.sin(seat.angle) * RING_RY);
      const row = sheet.rows[facing] ?? 0;
      const column = frameIndex(sheet, seat.animTime, false);
      const image = this.sprites.image(PLAYER_SHEET, seat.color);
      const drawX = Math.round(x - sheet.frameWidth / 2);
      const drawY = Math.round(y - sheet.frameHeight) + bob;

      ctx.save();
      ctx.globalAlpha = alpha;

      // Contact shadow. Without it everyone looks pasted onto the ground.
      ctx.fillStyle = tone.entity.shadow;
      ctx.beginPath();
      ctx.ellipse(Math.round(x), Math.round(y), 5, 2, 0, 0, TAU);
      ctx.fill();

      // The local player gets a ring in their own colour, pulsing at the same
      // rate as the fire so it belongs to the scene rather than to the UI.
      if (seat.isLocal) {
        ctx.globalAlpha = alpha * (0.3 + this.flicker * 0.35);
        ctx.strokeStyle = seat.color;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.ellipse(Math.round(x), Math.round(y), 8, 3.5, 0, 0, TAU);
        ctx.stroke();
        ctx.globalAlpha = alpha;
      }

      if (image) {
        ctx.drawImage(
          image,
          column * sheet.frameWidth,
          row * sheet.frameHeight,
          sheet.frameWidth,
          sheet.frameHeight,
          drawX,
          drawY,
          sheet.frameWidth,
          sheet.frameHeight,
        );
        // Firelight on the body: a warm wash that breathes, masked to the
        // sprite so it lands on the character and not on the ground behind it.
        ctx.globalCompositeOperation = 'lighter';
        ctx.globalAlpha = alpha * 0.1 * this.flicker;
        ctx.drawImage(
          this.sprites.image(PLAYER_SHEET, palette().fire.core) ?? image,
          column * sheet.frameWidth,
          row * sheet.frameHeight,
          sheet.frameWidth,
          sheet.frameHeight,
          drawX,
          drawY,
          sheet.frameWidth,
          sheet.frameHeight,
        );
        ctx.globalCompositeOperation = 'source-over';
      }

      if (seat.isHost) {
        ctx.globalAlpha = alpha;
        ctx.fillStyle = tone.inkAccent;
        // A four-point crown, five pixels wide, sitting above the head.
        ctx.fillRect(drawX + 5, drawY - 4, 6, 1);
        ctx.fillRect(drawX + 5, drawY - 6, 1, 2);
        ctx.fillRect(drawX + 7, drawY - 5, 1, 1);
        ctx.fillRect(drawX + 10, drawY - 6, 1, 2);
      }
      ctx.restore();
    }
  }

  /** 0..1 body opacity: fades in during a summon, out during a departure. */
  private seatAlpha(seat: Seat): number {
    if (seat.phase === 'leaving') return 1 - clamp01(seat.t / LEAVE_TIME);
    if (seat.phase === 'summoning') {
      const progress = clamp01(seat.t / SUMMON_TIME);
      return clamp01((progress - BODY_FADE_IN) / (BODY_LANDED - BODY_FADE_IN));
    }
    return 1;
  }

  private drawParticles(): void {
    const { ctx } = this;
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    for (const p of this.particles) {
      if (p.age < 0) continue;
      ctx.globalAlpha = clamp01(1 - p.age / p.life);
      ctx.fillStyle = p.color;
      ctx.fillRect(Math.round(p.x), Math.round(p.y), p.size, p.size);
    }
    ctx.restore();
  }

  private drawRings(): void {
    const { ctx } = this;
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    for (const ring of this.rings) {
      if (ring.age < 0) continue;
      const progress = clamp01(ring.age / ring.life);
      const radius = ring.maxRadius * progress ** 0.55;
      ctx.globalAlpha = (1 - progress) * 0.75;
      ctx.strokeStyle = ring.color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      // Flattened: the wave travels along the ground, not through the air.
      ctx.ellipse(ring.x, ring.y, radius, radius * 0.42, 0, 0, TAU);
      ctx.stroke();
    }
    ctx.restore();
  }

  /**
   * Names, in screen space.
   *
   * Departure Mono is a pixel face and is only crisp at multiples of 11 px, so
   * labels are drawn at the real screen scale instead of being blown up with
   * the rest of the scene.
   */
  private drawLabels(): void {
    const { ctx } = this;
    const tone = palette();
    const size = HUD_GRID * Math.max(1, Math.round(this.dpr));

    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.font = hudFont(size);
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';

    for (const seat of this.seats) {
      const alpha = this.seatAlpha(seat);
      if (alpha <= 0.05) continue;
      const { x, y } = seatPosition(seat.angle);
      const sx = Math.round(this.originX + x * this.zoom);
      const sy = Math.round(this.originY + y * this.zoom + size * 1.6);

      ctx.globalAlpha = alpha;
      ctx.fillStyle = tone.entity.labelShadow;
      ctx.fillText(seat.name, sx + 1, sy + 1);
      ctx.fillStyle = seat.isLocal ? tone.ink : tone.inkMuted;
      ctx.fillText(seat.name, sx, sy);
    }
    ctx.restore();
  }
}

/** Even spacing round the ring, with the front seat (nearest the camera) first. */
function seatAngle(index: number, total: number): number {
  return Math.PI / 2 + (index / Math.max(1, total)) * TAU;
}

function seatPosition(angle: number): { x: number; y: number } {
  return { x: Math.cos(angle) * RING_RX, y: Math.sin(angle) * RING_RY };
}

/**
 * The same angle, expressed as the closest one to `from`.
 *
 * Without this a seat re-spacing from 350° to 10° eases the long way round and
 * walks a player backwards through the whole party.
 */
function nearestTurn(from: number, to: number): number {
  let delta = (to - from) % TAU;
  if (delta > Math.PI) delta -= TAU;
  if (delta < -Math.PI) delta += TAU;
  return from + delta;
}
