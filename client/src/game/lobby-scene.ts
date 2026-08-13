/**
 * The campfire clearing: the lobby's canvas, and the title screen's backdrop.
 *
 * This is a scene, not a game. Nothing is authoritative, nothing is predicted,
 * no input is read — the party standing around the fire is the roster the
 * server broadcast, drawn.
 *
 * It is, however, the SAME forest. The ground, trees, rocks, grass and ferns
 * come out of `render/terrain` and are painted by the arena's own
 * `TerrainLayer`, over a `TileMap` generated here rather than sent by a server.
 * That reuse is the point: swaying grass, canopies that close over a character
 * and the seamless floor atlas all arrive for free, and the lobby cannot drift
 * away from the look of the game it opens into. The fire itself is a generated
 * animated prop (`campfire.png`, see server/tools/make_textures.py), not shapes
 * drawn with canvas calls.
 *
 * World units are the game's own pixels; the whole scene is blitted through an
 * integer camera zoom so the art stays on its pixel grid. The one exception is
 * text: names are drawn in SCREEN space after the world pass, because Departure
 * Mono is only crisp at multiples of 11 screen px.
 *
 * Lifecycle is explicit — `start()` / `dispose()`, same contract as `Game`.
 */

import { get2d } from "../lib/canvas";
import { clamp, clamp01, lerp } from "../lib/math";
import { Camera } from "../render/camera";
import { TerrainLayer } from "../render/layers/terrain";
import { frameIndex, SpriteBook } from "../render/sprites";
import { loadTerrain, type TerrainAtlas, tileHash } from "../render/terrain";
import { HUD_GRID, hudFont, whenFontsReady } from "../theme/fonts";
import { palette } from "../theme/palette";
import { FLOOR, ROCK, TileMap, TREE } from "./world";

const TAU = Math.PI * 2;
/** Sprite sheet every seated player is drawn from. */
const PLAYER_SHEET = "player";
/** Art scale if the terrain manifest is missing; it is the authority normally. */
const FALLBACK_TILE = 16;

/** The clearing, in tiles. Big enough that the camera never sees an edge. */
const MAP_TILES_W = 46;
const MAP_TILES_H = 32;
/** Open ground around the fire, in tiles, before the treeline starts. */
const CLEARING_TILES = 6.4;
/** How many tiles of forest the camera should frame. Decides the zoom. */
const VIEW_TILES_W = 26;
const VIEW_TILES_H = 17;

/** Seat ring, in tiles. Elliptical: a circle reads as a flat disc from here. */
const RING_TILES_X = 3.5;
const RING_TILES_Y = 2.0;
/** How fast a seat slides to its new angle when the party grows. */
const RESEAT_RATE = 3.2;

/** Seconds a player spends materialising, and dissolving. */
const SUMMON_TIME = 1.05;
const LEAVE_TIME = 0.45;
/** When in the summon the body starts to appear, and when it has fully landed. */
const BODY_FADE_IN = 0.42;
const BODY_LANDED = 0.72;

/** Embers per second thrown by the fire, on top of the ones in the sprite. */
const EMBER_RATE = 14;

export interface LobbyMember {
	id: string;
	name: string;
	color: string;
	isLocal: boolean;
	isHost: boolean;
}

type SeatPhase = "summoning" | "seated" | "leaving";

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
	/** Gravity, world px per second squared. */
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
	private readonly terrain = new TerrainLayer();
	private readonly camera = new Camera();

	private readonly seats: Seat[] = [];
	private readonly particles: Particle[] = [];
	private readonly rings: Ring[] = [];
	/** Members handed in before `start()` finished loading the atlas. */
	private pending: readonly LobbyMember[] | null = null;

	private atlas: TerrainAtlas | null = null;
	private world: TileMap | null = null;
	private resizeObserver: ResizeObserver | null = null;
	private rafId: number | null = null;
	private started = false;
	private disposed = false;
	private resizeDirty = true;

	private tile = FALLBACK_TILE;
	private dpr = 1;
	/** The fire's base, in world pixels — the anchor for seats and light. */
	private fireX = 0;
	private fireY = 0;
	private time = 0;
	private lastFrame = 0;
	private emberDebt = 0;
	/** 0..1 flame brightness, driven by layered sines. Read by every lit thing. */
	private flicker = 1;

	constructor(
		canvas: HTMLCanvasElement,
		/** Seed for the clearing. Two rooms should not be the same forest. */
		private readonly seed = 1,
		sprites: SpriteBook = new SpriteBook(),
	) {
		this.canvas = canvas;
		this.ctx = get2d(canvas, "lobby-scene");
		this.sprites = sprites;
	}

	async start(): Promise<void> {
		if (this.started || this.disposed) return;
		this.started = true;

		// The webfont too: names drawn in the fallback face and then swapped is the
		// one flicker in this scene that is not on purpose.
		const [, atlas] = await Promise.all([
			this.sprites.load([PLAYER_SHEET]),
			loadTerrain(),
			whenFontsReady(),
		]);
		if (this.disposed) return;

		this.atlas = atlas;
		// The manifest is the authority on art scale — the lobby has no server
		// config to read `tileSize` from, and inventing one here would put the
		// clearing on a different grid from the arena's.
		this.tile = atlas?.groundTile ?? FALLBACK_TILE;
		this.terrain.setAtlas(atlas);
		this.world = buildClearing(this.seed, this.tile);
		this.fireX = (Math.floor(MAP_TILES_W / 2) + 0.5) * this.tile;
		this.fireY = (Math.floor(MAP_TILES_H / 2) + 1) * this.tile;
		if (this.pending) {
			const members = this.pending;
			this.pending = null;
			this.setMembers(members);
		}

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
		this.terrain.reset();
		this.seats.length = 0;
		this.particles.length = 0;
		this.rings.length = 0;
		this.world = null;
		this.atlas = null;
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
		// Before the atlas lands there is no world to place a seat in. Hold the
		// roster rather than dropping it — the first one arrives during loading.
		if (!this.world) {
			this.pending = members;
			return;
		}

		const ordered = [...members].sort(
			(a, b) => Number(b.isLocal) - Number(a.isLocal),
		);
		const live = new Set(ordered.map((m) => m.id));

		for (const seat of this.seats) {
			if (seat.phase !== "leaving" && !live.has(seat.id)) {
				seat.phase = "leaving";
				seat.t = 0;
				this.spawnDeparture(seat);
			}
		}

		ordered.forEach((member, index) => {
			const angle = seatAngle(index, ordered.length);
			const existing = this.seats.find(
				(s) => s.id === member.id && s.phase !== "leaving",
			);
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
				phase: "summoning",
				t: 0,
				bobPhase: Math.random() * TAU,
			};
			this.seats.push(seat);
			this.spawnSummon(seat);
		});
	}

	// --- geometry ------------------------------------------------------------
	private seatPosition(angle: number): { x: number; y: number } {
		return {
			x: this.fireX + Math.cos(angle) * RING_TILES_X * this.tile,
			y: this.fireY + Math.sin(angle) * RING_TILES_Y * this.tile,
		};
	}

	// --- vfx -----------------------------------------------------------------
	/** A column of motes falling out of the dark onto an empty seat. */
	private spawnSummon(seat: Seat): void {
		const { x, y } = this.seatPosition(seat.angle);
		const ts = this.tile;
		const tone = palette().summon;
		for (let i = 0; i < 34; i++) {
			const spread = (Math.random() * 2 - 1) * ts * 0.7;
			const startY = y - ts * (5.5 + Math.random() * 9);
			this.particles.push({
				x: x + spread,
				y: startY,
				sx: x + spread,
				sy: startY,
				tx: x + spread * 0.15,
				ty: y - Math.random() * ts * 0.75,
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
		const { x, y } = this.seatPosition(seat.angle);
		const ts = this.tile;
		const tone = palette().summon;
		this.rings.push({
			x,
			y,
			age: 0,
			life: 0.5,
			maxRadius: ts * 1.6,
			color: tone.core,
		});
		this.rings.push({
			x,
			y,
			age: -0.08,
			life: 0.62,
			maxRadius: ts * 2.4,
			color: seat.color,
		});
		for (let i = 0; i < 16; i++) {
			const angle = Math.random() * TAU;
			const speed = ts * (1.5 + Math.random() * 2.9);
			this.particles.push({
				x,
				y,
				vx: Math.cos(angle) * speed,
				vy: Math.sin(angle) * speed * 0.45 - ts * 0.9,
				gy: ts * 5.6,
				age: 0,
				life: 0.35 + Math.random() * 0.4,
				size: 1,
				color: i % 3 === 0 ? seat.color : tone.spark,
			});
		}
	}

	private spawnDeparture(seat: Seat): void {
		const { x, y } = this.seatPosition(seat.angle);
		const ts = this.tile;
		for (let i = 0; i < 18; i++) {
			this.particles.push({
				x: x + (Math.random() * 2 - 1) * ts * 0.3,
				y: y - Math.random() * ts * 0.9,
				vx: (Math.random() * 2 - 1) * ts * 0.75,
				vy: -ts * (1.1 + Math.random() * 1.6),
				gy: -ts * 0.4,
				age: 0,
				life: 0.45 + Math.random() * 0.35,
				size: 1,
				color: seat.color,
			});
		}
	}

	/**
	 * Live embers on top of the ones baked into the sprite loop.
	 *
	 * The sprite's own sparks sell the fire at rest; these are what make it feel
	 * like it is in a space — they drift off the frame, past the seated players,
	 * and are not on an eight-frame cycle.
	 */
	private spawnEmbers(dt: number): void {
		this.emberDebt += dt * EMBER_RATE * (0.6 + this.flicker * 0.7);
		const ts = this.tile;
		const tones = palette().fire.embers;
		while (this.emberDebt >= 1) {
			this.emberDebt -= 1;
			this.particles.push({
				x: this.fireX + (Math.random() * 2 - 1) * ts * 0.3,
				y: this.fireY - ts * (0.4 + Math.random() * 0.5),
				vx: (Math.random() * 2 - 1) * ts * 0.55,
				vy: -ts * (1.4 + Math.random() * 1.6),
				// Embers slow as they cool, so gravity is a gentle brake, not a fall.
				gy: ts * 0.45,
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
		const { canvas, world } = this;
		this.dpr = Math.min(2, window.devicePixelRatio || 1);
		const width = Math.max(1, Math.round(canvas.clientWidth * this.dpr));
		const height = Math.max(1, Math.round(canvas.clientHeight * this.dpr));
		if (canvas.width !== width) canvas.width = width;
		if (canvas.height !== height) canvas.height = height;
		// Resizing the backing store resets context state.
		this.ctx.imageSmoothingEnabled = false;

		// Integer zoom only: a fractional one puts the sprite grid between screen
		// pixels and the whole scene goes soft.
		this.camera.zoom = clamp(
			Math.floor(
				Math.min(
					width / (VIEW_TILES_W * this.tile),
					height / (VIEW_TILES_H * this.tile),
				),
			),
			2,
			6,
		);
		this.camera.resize(width, height);
		if (world) {
			// The fire sits above centre so the front row has room to stand.
			this.camera.snapTo(this.fireX, this.fireY + this.tile * 1.2, world);
		}
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
			seat.angle = lerp(
				seat.angle,
				seat.targetAngle,
				1 - Math.exp(-RESEAT_RATE * dt),
			);
			if (seat.phase === "summoning") {
				// The shockwave fires the moment the body finishes resolving.
				if (
					seat.t >= BODY_LANDED * SUMMON_TIME &&
					seat.t - dt < BODY_LANDED * SUMMON_TIME
				) {
					this.spawnLanding(seat);
				}
				if (seat.t >= SUMMON_TIME) {
					seat.phase = "seated";
					seat.t = 0;
				}
			}
		}
		// Departed seats leave the array only once their dissolve has played out.
		for (let i = this.seats.length - 1; i >= 0; i--) {
			if (this.seats[i].phase === "leaving" && this.seats[i].t >= LEAVE_TIME) {
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
		const { ctx, canvas, camera, world } = this;
		const tone = palette();

		ctx.setTransform(1, 0, 0, 1, 0, 0);
		ctx.fillStyle = tone.surface;
		ctx.fillRect(0, 0, canvas.width, canvas.height);
		if (!world) return;

		ctx.save();
		ctx.scale(camera.zoom, camera.zoom);
		ctx.translate(-camera.renderX, -camera.renderY);

		this.terrain.ground(ctx, world, camera, this.time);
		this.drawFirelight();
		this.drawBeams();
		this.drawStanding();
		this.drawParticles();
		this.drawRings();
		// Canopies and ferns close over whoever is standing behind them, exactly
		// as they do in the arena.
		this.terrain.overgrowth(ctx, world, camera, this.time);
		this.drawNight();

		ctx.restore();
		this.drawLabels();
	}

	/** The warm pool the fire throws on the ground. Breathes with the flicker. */
	private drawFirelight(): void {
		const { ctx } = this;
		const glow = palette().fire.glow.join(" ");
		const radius = this.tile * (6 + this.flicker * 1.8);
		const cy = this.fireY - this.tile * 0.4;

		ctx.save();
		ctx.globalCompositeOperation = "lighter";
		const gradient = ctx.createRadialGradient(
			this.fireX,
			cy,
			2,
			this.fireX,
			cy,
			radius,
		);
		gradient.addColorStop(
			0,
			`rgb(${glow} / ${(0.42 * this.flicker).toFixed(3)})`,
		);
		gradient.addColorStop(
			0.38,
			`rgb(${glow} / ${(0.15 * this.flicker).toFixed(3)})`,
		);
		gradient.addColorStop(1, `rgb(${glow} / 0)`);
		ctx.fillStyle = gradient;
		ctx.fillRect(this.fireX - radius, cy - radius, radius * 2, radius * 2);
		ctx.restore();
	}

	/** Everything past the fire's reach is night, not floor. */
	private drawNight(): void {
		const { ctx, camera } = this;
		const tone = palette();
		const reach = Math.hypot(camera.viewWidth, camera.viewHeight) * 0.62;
		const gradient = ctx.createRadialGradient(
			this.fireX,
			this.fireY,
			this.tile * 2,
			this.fireX,
			this.fireY,
			reach,
		);
		gradient.addColorStop(0, "rgb(0 0 0 / 0)");
		gradient.addColorStop(0.42, `rgb(${tone.night.shadow.join(" ")} / 0.5)`);
		gradient.addColorStop(0.78, `rgb(${tone.night.shadow.join(" ")} / 0.93)`);
		gradient.addColorStop(1, tone.surface);
		ctx.fillStyle = gradient;
		ctx.fillRect(
			camera.renderX,
			camera.renderY,
			camera.viewWidth,
			camera.viewHeight,
		);
	}

	/**
	 * The fire and the party, painted back to front.
	 *
	 * The campfire is in this sort rather than drawn before it: a player seated
	 * on the near side of the pit has to overlap the flame, and one behind it has
	 * to be hidden by it. Drawing the fire as a background would flatten the ring
	 * into a row of characters standing in front of a picture of a fire.
	 */
	private drawStanding(): void {
		const entries: { y: number; draw: () => void }[] = [
			{ y: this.fireY, draw: () => this.drawCampfire() },
		];
		for (const seat of this.seats) {
			entries.push({
				y: this.seatPosition(seat.angle).y,
				draw: () => this.drawSeat(seat),
			});
		}
		entries.sort((a, b) => a.y - b.y);
		for (const entry of entries) entry.draw();
	}

	private drawCampfire(): void {
		const sheet = this.atlas?.campfire;
		if (!sheet) return;
		const { ctx } = this;
		// The frames are a loop, not variants — see `fps` in the terrain manifest.
		const frame =
			sheet.fps > 0 ? Math.floor(this.time * sheet.fps) % sheet.frames : 0;
		ctx.drawImage(
			sheet.image,
			frame * sheet.frameWidth,
			0,
			sheet.frameWidth,
			sheet.frameHeight,
			Math.round(this.fireX - sheet.frameWidth / 2),
			Math.round(this.fireY - sheet.frameHeight),
			sheet.frameWidth,
			sheet.frameHeight,
		);
	}

	/**
	 * One seated player.
	 *
	 * Everybody faces the camera. They are arranged around the fire, but a ring
	 * of characters drawn with their backs to the viewer is a ring of anonymous
	 * shoulders — and the roster on the left is keyed to colours you can only
	 * match to a face you can see.
	 */
	private drawSeat(seat: Seat): void {
		const { ctx } = this;
		const sheet = this.sprites.get(PLAYER_SHEET);
		if (!sheet) return;

		const alpha = this.seatAlpha(seat);
		if (alpha <= 0.01) return;

		const { x, y } = this.seatPosition(seat.angle);
		const tone = palette();
		const bob = Math.round(Math.sin(this.time * 1.7 + seat.bobPhase));
		const row = sheet.rows.down ?? 0;
		const column = frameIndex(sheet, 0, false);
		const image = this.sprites.image(PLAYER_SHEET, seat.color);
		const drawX = Math.round(x - sheet.frameWidth / 2);
		const drawY = Math.round(y - sheet.frameHeight) + bob;

		ctx.save();
		ctx.globalAlpha = alpha;

		// Contact shadow. Without it everyone looks pasted onto the ground.
		ctx.fillStyle = tone.entity.shadow;
		ctx.beginPath();
		ctx.ellipse(
			Math.round(x),
			Math.round(y),
			this.tile * 0.3,
			this.tile * 0.12,
			0,
			0,
			TAU,
		);
		ctx.fill();

		// The local player gets a ring in their own colour, pulsing at the same
		// rate as the fire so it belongs to the scene rather than to the UI.
		if (seat.isLocal) {
			ctx.globalAlpha = alpha * (0.3 + this.flicker * 0.35);
			ctx.strokeStyle = seat.color;
			ctx.lineWidth = 1;
			ctx.beginPath();
			ctx.ellipse(
				Math.round(x),
				Math.round(y),
				this.tile * 0.5,
				this.tile * 0.22,
				0,
				0,
				TAU,
			);
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
			// Firelight on the body: a warm wash that breathes, masked to the sprite
			// so it lands on the character and not on the ground behind it. Weaker
			// the further round the ring you are.
			const facing = 0.55 + 0.45 * Math.max(0, Math.sin(seat.angle));
			ctx.globalCompositeOperation = "lighter";
			ctx.globalAlpha = alpha * 0.12 * this.flicker * facing;
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
			ctx.globalCompositeOperation = "source-over";
		}

		if (seat.isHost) {
			ctx.globalAlpha = alpha;
			ctx.fillStyle = tone.inkAccent;
			// A four-point crown, six pixels wide, sitting above the head.
			ctx.fillRect(drawX + 5, drawY - 4, 6, 1);
			ctx.fillRect(drawX + 5, drawY - 6, 1, 2);
			ctx.fillRect(drawX + 7, drawY - 5, 1, 1);
			ctx.fillRect(drawX + 10, drawY - 6, 1, 2);
		}
		ctx.restore();
	}

	/** 0..1 body opacity: fades in during a summon, out during a departure. */
	private seatAlpha(seat: Seat): number {
		if (seat.phase === "leaving") return 1 - clamp01(seat.t / LEAVE_TIME);
		if (seat.phase === "summoning") {
			const progress = clamp01(seat.t / SUMMON_TIME);
			return clamp01((progress - BODY_FADE_IN) / (BODY_LANDED - BODY_FADE_IN));
		}
		return 1;
	}

	/** The summoning column, falling out of the top of the view. */
	private drawBeams(): void {
		const { ctx, camera } = this;
		const beam = palette().summon.beam.join(" ");
		const top = camera.renderY;

		ctx.save();
		ctx.globalCompositeOperation = "lighter";
		for (const seat of this.seats) {
			if (seat.phase !== "summoning") continue;
			const progress = clamp01(seat.t / SUMMON_TIME);
			const { x, y } = this.seatPosition(seat.angle);
			const strength = Math.sin(Math.PI * progress) ** 0.7;
			const width = this.tile * (0.2 + strength * 0.6);

			const gradient = ctx.createLinearGradient(0, top, 0, y);
			gradient.addColorStop(0, `rgb(${beam} / 0)`);
			gradient.addColorStop(
				0.55,
				`rgb(${beam} / ${(0.16 * strength).toFixed(3)})`,
			);
			gradient.addColorStop(
				1,
				`rgb(${beam} / ${(0.42 * strength).toFixed(3)})`,
			);
			ctx.fillStyle = gradient;
			ctx.fillRect(x - width / 2, top, width, y - top);
		}
		ctx.restore();
	}

	private drawParticles(): void {
		const { ctx } = this;
		ctx.save();
		ctx.globalCompositeOperation = "lighter";
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
		ctx.globalCompositeOperation = "lighter";
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
		const { ctx, camera } = this;
		const tone = palette();
		const size = HUD_GRID * Math.max(1, Math.round(this.dpr));

		ctx.save();
		ctx.setTransform(1, 0, 0, 1, 0, 0);
		ctx.font = hudFont(size);
		ctx.textAlign = "center";
		ctx.textBaseline = "bottom";

		for (const seat of this.seats) {
			const alpha = this.seatAlpha(seat);
			if (alpha <= 0.05) continue;
			const { x, y } = this.seatPosition(seat.angle);
			const sx = Math.round((x - camera.renderX) * camera.zoom);
			const sy = Math.round((y - camera.renderY) * camera.zoom + size * 1.5);

			ctx.globalAlpha = alpha;
			ctx.fillStyle = tone.entity.labelShadow;
			ctx.fillText(seat.name, sx + 1, sy + 1);
			ctx.fillStyle = seat.isLocal ? tone.ink : tone.inkMuted;
			ctx.fillText(seat.name, sx, sy);
		}
		ctx.restore();
	}
}

/**
 * A clearing in the forest, generated the same way the arena's map is: one
 * seed, hashed with the tile coordinate. Open ground in the middle for the
 * fire and the party, a ragged treeline closing in, and a solid wall of trunks
 * at the border so the camera never frames the end of the world.
 */
function buildClearing(seed: number, tile: number): TileMap {
	const cx = (MAP_TILES_W - 1) / 2;
	const cy = (MAP_TILES_H - 1) / 2;
	const tiles: number[][] = [];

	for (let ty = 0; ty < MAP_TILES_H; ty++) {
		const row: number[] = [];
		for (let tx = 0; tx < MAP_TILES_W; tx++) {
			row.push(clearingTile(tx, ty, cx, cy, seed));
		}
		tiles.push(row);
	}

	return new TileMap({
		width: MAP_TILES_W,
		height: MAP_TILES_H,
		tileSize: tile,
		seed,
		tiles,
	});
}

function clearingTile(
	tx: number,
	ty: number,
	cx: number,
	cy: number,
	seed: number,
): number {
	if (tx < 2 || ty < 2 || tx >= MAP_TILES_W - 2 || ty >= MAP_TILES_H - 2)
		return TREE;

	// Squashed vertically to match the ellipse the seats sit on and the shape of
	// a landscape viewport — a circular clearing reads as a bulge on a wide screen.
	const dx = tx - cx;
	const dy = (ty - cy) * 1.45;
	const distance = Math.hypot(dx, dy);
	// A ragged edge, not a stamped circle.
	const edge = CLEARING_TILES + tileHash(tx, ty, seed, 7) * 1.8 - 0.9;

	if (distance < edge) {
		// A couple of boulders inside the clearing, kept off the seat ring.
		if (distance > RING_TILES_X + 0.8 && tileHash(tx, ty, seed, 8) > 0.94)
			return ROCK;
		return FLOOR;
	}

	// Density ramps with depth so the treeline thickens instead of starting solid.
	const depth = clamp01((distance - edge) / 5);
	if (tileHash(tx, ty, seed, 9) < 0.16 + depth * 0.66) return TREE;
	if (tileHash(tx, ty, seed, 10) < 0.05 + depth * 0.06) return ROCK;
	return FLOOR;
}

/** Even spacing round the ring, with the front seat (nearest the camera) first. */
function seatAngle(index: number, total: number): number {
	return Math.PI / 2 + (index / Math.max(1, total)) * TAU;
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
