/**
 * The campfire clearing: the lobby's canvas, and the title screen's backdrop.
 *
 * This is a scene, not a game. Nothing is authoritative, nothing is predicted,
 * no input is read — the party standing around the fire is the roster the
 * server broadcast, drawn.
 *
 * It is not a picture of the camp. It is THE camp: the tiles come down in
 * `hello` (see `setCamp`) and the players stand on the coordinates the
 * simulation is already holding for them, so the seat somebody is sitting on
 * here is the tile they walk off when the host presses start. Nothing teleports
 * at the transition because there is nothing to teleport between. The title
 * screen is the one caller with no server, and it falls back to a clearing
 * generated locally — the shot there only has to look like the place, since
 * nobody is standing in it.
 *
 * The ground, trees, rocks, grass and ferns are painted by the arena's own
 * `TerrainLayer`. That reuse is the point: swaying grass, canopies that close
 * over a character and the seamless floor atlas all arrive for free, and the
 * lobby cannot drift away from the look of the game it opens into. The fire
 * itself is a generated animated prop (`campfire.png`, see
 * server/tools/make_textures.py), not shapes drawn with canvas calls.
 *
 * World units are the game's own pixels; the whole scene is blitted through an
 * integer camera zoom so the art stays on its pixel grid — the SAME zoom the
 * arena's arrival opens on (see `render/framing.ts`), which is what makes the
 * push-in read as a camera move rather than as a cut. The one exception is
 * text: names are drawn in SCREEN space after the world pass, because Departure
 * Mono is only crisp at multiples of 11 screen px.
 *
 * Lifecycle is explicit — `start()` / `dispose()`, same contract as `Game`.
 */

import { get2d } from "../lib/canvas";
import { clamp01, lerp } from "../lib/math";
import type { GameConfig, MapPayload } from "../net/protocol";
import { Camera } from "../render/camera";
import { FovField, type LightSource } from "../render/fov";
import { ARENA_ZOOM, campZoom } from "../render/framing";
import { DarknessLayer } from "../render/layers/darkness";
import { TerrainLayer } from "../render/layers/terrain";
import { frameIndex, SpriteBook } from "../render/sprites";
import { loadTerrain, type TerrainAtlas, tileHash } from "../render/terrain";
import {
	effectFrame,
	effectImage,
	loadVfx,
	type VfxAtlas,
} from "../render/vfx";
import { HUD_GRID, hudFont, whenFontsReady } from "../theme/fonts";
import { palette } from "../theme/palette";
import { FIRE, FLOOR, hearthMask, ROCK, TileMap, TREE } from "./world";

const TAU = Math.PI * 2;
/** Sprite sheet every seated player is drawn from. */
const PLAYER_SHEET = "player";
/** Art scale if the terrain manifest is missing; it is the authority normally. */
const FALLBACK_TILE = 16;

/**
 * The FALLBACK clearing, in tiles — the title screen's backdrop, generated
 * locally because there is no room and therefore no server. A real lobby throws
 * all of this away and draws `hello.map` instead.
 *
 * These are deliberate near-copies of the authoritative numbers in
 * server/app/camp.py. They do not have to agree to the pixel — nobody stands in
 * this one — they have to make the same kind of clearing.
 */
const MAP_TILES_W = 46;
const MAP_TILES_H = 32;
/** Open ground around the fire, in tiles, before the treeline starts. */
const CLEARING_TILES = 8.2;
/**
 * The hearth: the fire plus the ring of players around it, in tiles.
 *
 * Nothing decorative may stand inside this — no trees, no boulders, no grass,
 * no ferns. It is comfortably wider than the seat ring (RING_TILES_X) because
 * "does not overlap a player" is not the bar; the bar is that the party reads
 * as a group sitting in cleared ground, which needs empty floor around them.
 */
const HEARTH_TILES = 5.6;

/** Seat ring, in tiles. Elliptical: a circle reads as a flat disc from here. */
const RING_TILES_X = 3.5;
const RING_TILES_Y = 2.0;
/** How fast a seat slides to a new position when the party re-spaces. */
const RESEAT_RATE = 3.2;

/**
 * Seconds a player spends materialising.
 *
 * The summon sheet is the clock: 14 frames at 14 fps. Overriding it here would
 * either cut the collapse off or leave a dead beat after the beam has gone.
 */
const SUMMON_TIME = 1.0;
const LEAVE_TIME = 0.45;
/**
 * Normalized moment the beam hits the ground. Mirrors `IMPACT_AT` in
 * server/tools/make_vfx.py — the body has to finish resolving on the same
 * frame the sprite flashes, or the arrival lands twice.
 */
const SUMMON_IMPACT = 0.52;
/** When in the summon the body starts to appear, and when it has fully landed. */
const BODY_FADE_IN = 0.34;
const BODY_LANDED = SUMMON_IMPACT;
/**
 * Squash-and-stretch after touchdown, in seconds. The body arrives compressed
 * and springs back — a character that simply becomes opaque has been faded in,
 * not delivered.
 */
const LANDING_SETTLE = 0.24;

/** Embers per second thrown by the fire, on top of the ones in the sprite. */
const EMBER_RATE = 14;

/**
 * Vision numbers for a scene with no server to ask. Only the fire lights this
 * place — there are no viewers, so the lantern reach and cone are never read;
 * they exist because `FovField` takes one config for both kinds of light.
 */
const FALLBACK_VISION = { ambientTiles: 3.5, lanternTiles: 11, coneDegrees: 75 };
/** How far the fire reaches without a server saying. Mirrors config.py. */
const FALLBACK_FIRE_TILES = 10;

export interface LobbyMember {
	id: string;
	name: string;
	color: string;
	isLocal: boolean;
	isHost: boolean;
	/**
	 * Where the server says this player is, in world pixels — the centre of
	 * their collision box, exactly as a snapshot would carry it. The scene
	 * converts it to a contact point on the ground and never invents one.
	 */
	x: number;
	y: number;
}

/** The camp, once it has arrived. Until then the scene draws its fallback. */
export interface CampView {
	map: MapPayload;
	config: GameConfig;
}

type SeatPhase = "summoning" | "seated" | "leaving";

interface Seat {
	id: string;
	name: string;
	color: string;
	isLocal: boolean;
	isHost: boolean;
	/**
	 * Current and desired CONTACT POINT — where the feet are, in world pixels.
	 * The current one eases toward the target so a party re-spacing around the
	 * fire slides rather than snaps.
	 */
	x: number;
	y: number;
	targetX: number;
	targetY: number;
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
	/** Draw as a motion streak between last frame's position and this one. */
	streak?: boolean;
	/** Previous Y, written by `update`. Only meaningful with `streak`. */
	py?: number;
}

interface Ring {
	x: number;
	y: number;
	age: number;
	life: number;
	maxRadius: number;
	color: string;
}

/**
 * The move out of the lobby and into the run.
 *
 * Three things travel together over one eased progress: the framing slides from
 * the fire to the local player, the anchor slides from wherever the menu left
 * room to dead centre, and the scale pushes from the wide shot to `ARENA_ZOOM`.
 * They land on exactly the frame the arena's camera will open on, which is what
 * makes the handover between two different canvases invisible.
 */
interface Launch {
	elapsed: number;
	duration: number;
	fromAnchor: { x: number; y: number };
	fromZoom: number;
	/** Whose character the camera ends up on. Empty until a local seat exists. */
	focusId: string;
}

export class LobbyScene {
	private readonly canvas: HTMLCanvasElement;
	private readonly ctx: CanvasRenderingContext2D;
	private readonly sprites: SpriteBook;
	private readonly terrain = new TerrainLayer();
	private readonly darkness = new DarknessLayer();
	private readonly camera = new Camera();
	/**
	 * The same light field the arena runs, with the bonfire as its only source
	 * and nobody carrying a lamp. Sharing the system rather than drawing a
	 * gradient here is what stops the night changing shape at the handover —
	 * the camp is lit identically before and after the run starts, because it is
	 * lit by the same code.
	 */
	private fov: FovField | null = null;
	private lights: LightSource[] = [];

	private readonly seats: Seat[] = [];
	private readonly particles: Particle[] = [];
	private readonly rings: Ring[] = [];
	/** Members handed in before `start()` finished loading the atlas. */
	private pending: readonly LobbyMember[] | null = null;
	/** The server's camp, if this scene has one. Null on the title screen. */
	private camp: CampView | null = null;

	private atlas: TerrainAtlas | null = null;
	private vfx: VfxAtlas | null = null;
	private world: TileMap | null = null;
	private resizeObserver: ResizeObserver | null = null;
	private rafId: number | null = null;
	private started = false;
	private disposed = false;
	private resizeDirty = true;
	/** Running (or finished) launch. Null while the party is still gathering. */
	private launch: Launch | null = null;

	private tile = FALLBACK_TILE;
	private dpr = 1;
	/** Canvas size in CSS pixels. The zoom fit is decided in these, not device px. */
	private cssWidth = 0;
	private cssHeight = 0;
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
		/**
		 * Where the fire sits in the viewport, as 0..1 fractions. Both callers
		 * push it off-centre so their menu is not standing on top of it — and
		 * that displacement is half of what the launch takes back, which is why
		 * it is live state rather than a constructor-only framing decision.
		 */
		private anchor: { x: number; y: number } = { x: 0.5, y: 0.42 },
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
		const [, atlas, vfx] = await Promise.all([
			this.sprites.load([PLAYER_SHEET]),
			loadTerrain(),
			loadVfx(),
			whenFontsReady(),
		]);
		if (this.disposed) return;

		this.atlas = atlas;
		this.vfx = vfx;
		this.terrain.setAtlas(atlas);
		this.buildWorld();
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
		this.darkness.reset();
		this.seats.length = 0;
		this.particles.length = 0;
		this.rings.length = 0;
		this.world = null;
		this.fov = null;
		this.lights = [];
		this.atlas = null;
		this.vfx = null;
	}

	/**
	 * Move the fire's resting place in the viewport. Ignored once the launch
	 * has started, which owns the framing from then on.
	 */
	setAnchor(x: number, y: number): void {
		if (this.launch) return;
		this.anchor = { x, y };
		this.resizeDirty = true;
	}

	/**
	 * Leave the lobby: swoosh onto the local player and push in to game scale.
	 *
	 * This is the whole transition, and it happens HERE rather than in the
	 * arena because the lobby is already showing the place and the people. The
	 * menu slides off to the left while the camera takes back the room it was
	 * occupying, travels from the fire to your own character, and closes to
	 * `ARENA_ZOOM` — so by the last frame this scene draws, the picture is
	 * pixel-for-pixel what the arena is about to open on. The player never sees
	 * a cut, only a move that finishes.
	 *
	 * Idempotent: the host starts it on their own click and everybody else
	 * starts it when the phase flips, and both can happen to the same client.
	 */
	beginLaunch(duration: number): void {
		if (this.launch) return;
		// A room already in progress can launch before the first frame has sized
		// anything, which would capture a zoom the scene was never drawn at.
		if (this.cssWidth === 0) this.resize();
		this.launch = {
			elapsed: 0,
			duration,
			fromAnchor: { ...this.anchor },
			fromZoom: this.camera.zoom,
			focusId: this.seats.find((seat) => seat.isLocal)?.id ?? "",
		};
	}

	/** True once `beginLaunch` has run. The scene is on its way out. */
	get launching(): boolean {
		return this.launch !== null;
	}

	/**
	 * Hand the scene the camp the server sent.
	 *
	 * Safe at any time: before `start()` it is simply remembered, and after it
	 * the world is rebuilt in place. It arrives in `hello`, which lands before
	 * the first roster, so in practice the fallback clearing is never drawn in
	 * a real room.
	 */
	setCamp(camp: CampView | null): void {
		this.camp = camp;
		if (!this.atlas && !this.world) return;
		this.buildWorld();
		this.resizeDirty = true;
		// Seats were placed against the previous world's fire.
		for (const seat of this.seats) {
			seat.x = seat.targetX;
			seat.y = seat.targetY;
		}
	}

	/**
	 * Reconcile the drawn party with the roster.
	 *
	 * Arrivals get summoned rather than appearing: a player who blinks into
	 * existence reads as a rendering bug, and the whole point of the lobby is to
	 * make somebody joining feel like an event. Departures dissolve for the same
	 * reason.
	 *
	 * Where somebody stands is NOT this scene's decision. It used to force the
	 * local player into the front seat, which made "which one is me" free but
	 * meant every client was looking at a different party — and the instant the
	 * run started, everyone's characters jumped. Positions are the server's now;
	 * the local player is marked by the ring under their feet instead.
	 */
	setMembers(members: readonly LobbyMember[]): void {
		// Before the atlas lands there is no world to place a seat in. Hold the
		// roster rather than dropping it — the first one arrives during loading.
		if (!this.world) {
			this.pending = members;
			return;
		}

		const live = new Set(members.map((m) => m.id));
		for (const seat of this.seats) {
			if (seat.phase !== "leaving" && !live.has(seat.id)) {
				seat.phase = "leaving";
				seat.t = 0;
				this.spawnDeparture(seat);
			}
		}

		members.forEach((member, index) => {
			const { x, y } = this.contactPoint(member, index, members.length);
			const existing = this.seats.find(
				(s) => s.id === member.id && s.phase !== "leaving",
			);
			if (existing) {
				existing.name = member.name;
				existing.color = member.color;
				existing.isHost = member.isHost;
				existing.targetX = x;
				existing.targetY = y;
				return;
			}
			const seat: Seat = {
				id: member.id,
				name: member.name,
				color: member.color,
				isLocal: member.isLocal,
				isHost: member.isHost,
				x,
				y,
				targetX: x,
				targetY: y,
				phase: "summoning",
				t: 0,
				bobPhase: Math.random() * TAU,
			};
			this.seats.push(seat);
			this.spawnSummon(seat);
		});
	}

	// --- geometry ------------------------------------------------------------
	/**
	 * Where a member's feet touch the ground, in world pixels.
	 *
	 * The server sends the centre of the collision box, which is where the
	 * simulation keeps a player; the sprite is bottom-anchored, so the contact
	 * point is half a box lower. Getting this wrong is a party floating a few
	 * pixels above their own shadows.
	 *
	 * The ring fallback is for the title screen only, where there is no config
	 * to convert with and nobody to place.
	 */
	private contactPoint(
		member: LobbyMember,
		index: number,
		total: number,
	): { x: number; y: number } {
		const config = this.camp?.config;
		if (!config) {
			const angle = seatAngle(index, total);
			return {
				x: this.fireX + Math.cos(angle) * RING_TILES_X * this.tile,
				y: this.fireY + Math.sin(angle) * RING_TILES_Y * this.tile,
			};
		}
		return { x: member.x, y: member.y + config.playerHalfHeight };
	}

	/**
	 * (Re)build the tile map, the hearth mask and the fire anchor.
	 *
	 * One path for both sources: the server's camp if there is one, a locally
	 * generated clearing otherwise. Everything downstream reads `world.fires`,
	 * so neither branch has to be special-cased again after this.
	 */
	private buildWorld(): void {
		const camp = this.camp;
		// The manifest is the authority on art scale for the fallback — with no
		// server config to read `tileSize` from, inventing one here would put
		// the clearing on a different grid from the arena's.
		this.tile = camp?.map.tileSize ?? this.atlas?.groundTile ?? FALLBACK_TILE;
		this.world = camp
			? new TileMap(camp.map)
			: buildClearing(this.seed, this.tile);

		const fire = this.world.fires[0];
		this.fireX = fire?.x ?? this.world.pixelWidth / 2;
		this.fireY = fire?.y ?? this.world.pixelHeight / 2;

		this.fov = new FovField(this.world.width, this.world.height);
		this.lights = this.world.fires.map((place, index) => ({
			id: index,
			x: place.x,
			// Lifted off the contact row — the light comes from the flame, not
			// from the ashes. Same offset the arena applies.
			y: place.y - this.tile * 0.5,
			radiusTiles: camp?.config.campfireLightTiles ?? FALLBACK_FIRE_TILES,
		}));

		// Grass and ferns are placed by the terrain layer from the tile hash, so
		// keeping them out of the hearth has to be told to it — the map itself
		// only decides trees, rocks and the fire.
		this.terrain.setDecorationMask(
			hearthMask(
				this.world,
				camp?.config.hearthTiles ?? HEARTH_TILES,
				camp ? camp.config.ringTilesX / camp.config.ringTilesY : RING_TILES_X / RING_TILES_Y,
				tileHash,
			),
		);
	}

	// --- vfx -----------------------------------------------------------------
	/**
	 * Motes falling out of the dark onto an empty seat.
	 *
	 * The summon sheet is only six tiles tall, so these are what make the
	 * arrival come from ABOVE rather than from just off the top of a sprite:
	 * they start well outside the frame and converge into the column as it
	 * strikes. They also streak (see `drawParticles`) — a dot moving fast
	 * enough to cross tiles between frames reads as a stutter unless it leaves
	 * something behind.
	 */
	private spawnSummon(seat: Seat): void {
		const { x, y } = seat;
		const ts = this.tile;
		const tone = palette().summon;
		for (let i = 0; i < 38; i++) {
			const spread = (Math.random() * 2 - 1) * ts * 0.9;
			const startY = y - ts * (7 + Math.random() * 11);
			this.particles.push({
				x: x + spread,
				y: startY,
				sx: x + spread,
				sy: startY,
				tx: x + spread * 0.12,
				ty: y - Math.random() * ts * 0.75,
				vx: 0,
				vy: 0,
				gy: 0,
				// Staggered so they arrive as a volley, not a curtain. The last
				// of them lands as the beam does.
				age: -Math.random() * 0.4,
				life: SUMMON_TIME * (0.5 + Math.random() * 0.28),
				size: Math.random() < 0.22 ? 2 : 1,
				streak: true,
				// One in four wears the arriving player's colour, so even the
				// fall is theirs rather than a generic white.
				color:
					Math.random() < 0.26
						? seat.color
						: Math.random() < 0.4
							? tone.core
							: tone.spark,
			});
		}
	}

	/**
	 * The landing, in the arriving player's own colour.
	 *
	 * The white flash and the two shockwaves are baked into the summon sheet, so
	 * nothing here repeats them. What the sprite cannot know is WHO arrived —
	 * one ring and a spray of sparks in their roster colour is the whole job,
	 * and it is what ties the character in the scene to the row in the list.
	 */
	private spawnLanding(seat: Seat): void {
		const { x, y } = seat;
		const ts = this.tile;
		this.rings.push({
			x,
			y,
			age: 0,
			life: 0.66,
			maxRadius: ts * 2.6,
			color: seat.color,
		});
		for (let i = 0; i < 14; i++) {
			const angle = Math.random() * TAU;
			const speed = ts * (1.6 + Math.random() * 3.2);
			this.particles.push({
				x,
				y,
				vx: Math.cos(angle) * speed,
				vy: Math.sin(angle) * speed * 0.45 - ts * 1.1,
				gy: ts * 5.6,
				age: 0,
				life: 0.4 + Math.random() * 0.45,
				size: 1,
				color: seat.color,
			});
		}
	}

	private spawnDeparture(seat: Seat): void {
		const { x, y } = seat;
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
		const { canvas } = this;
		this.dpr = Math.min(2, window.devicePixelRatio || 1);
		this.cssWidth = Math.max(1, canvas.clientWidth);
		this.cssHeight = Math.max(1, canvas.clientHeight);
		const width = Math.max(1, Math.round(this.cssWidth * this.dpr));
		const height = Math.max(1, Math.round(this.cssHeight * this.dpr));
		if (canvas.width !== width) canvas.width = width;
		if (canvas.height !== height) canvas.height = height;
		// Resizing the backing store resets context state.
		this.ctx.imageSmoothingEnabled = false;
		this.frameCamera();
	}

	/**
	 * Point the camera. Called on resize, and every frame while launching.
	 *
	 * At rest the scale is an integer: a fractional one puts the sprite grid
	 * between screen pixels and the whole scene goes soft. The launch is allowed
	 * to pass through fractional scales because it is MOVING, and it lands
	 * exactly on `ARENA_ZOOM` — the scale the game itself is played at, so the
	 * arena opens on this frame rather than on a new one.
	 *
	 * The zoom fit is decided in CSS pixels and then multiplied by the device
	 * ratio. Deciding it in device pixels would frame half as much world on a
	 * hidpi screen as on a normal one, at the same physical size.
	 */
	private frameCamera(): void {
		const { world, dpr } = this;
		const rest = campZoom(this.cssWidth, this.cssHeight, this.tile);
		const launch = this.launch;

		let anchorX = this.anchor.x;
		let anchorY = this.anchor.y;
		let focusX = this.fireX;
		let focusY = this.fireY;
		let zoom = rest * dpr;

		if (launch) {
			const k = easeInOut(clamp01(launch.elapsed / launch.duration));
			// Log space: scale is multiplicative, and a linear ramp between two
			// zooms crawls at the wide end and then lunges at the tight one.
			zoom = Math.exp(
				lerp(Math.log(launch.fromZoom), Math.log(ARENA_ZOOM * dpr), k),
			);
			anchorX = lerp(launch.fromAnchor.x, 0.5, k);
			anchorY = lerp(launch.fromAnchor.y, 0.5, k);
			const target = this.launchTarget(launch);
			focusX = lerp(this.fireX, target.x, k);
			focusY = lerp(this.fireY, target.y, k);
		}

		this.camera.zoom = zoom;
		this.camera.resize(this.canvas.width, this.canvas.height);
		if (!world) return;
		// `snapTo` centres its target, so the point handed to it is displaced by
		// however far the anchor is from the middle. Clamping still applies: the
		// map is big enough that it never bites, but a smaller one would pull the
		// fire back toward centre rather than show the edge of the world.
		this.camera.snapTo(
			focusX + this.camera.viewWidth * (0.5 - anchorX),
			focusY + this.camera.viewHeight * (0.5 - anchorY),
			world,
		);
	}

	/**
	 * Where the launch is heading, in world pixels.
	 *
	 * The local player's BODY CENTRE, not the ground under their feet: that is
	 * the point the arena's camera follows, and landing on anything else would
	 * make the handover a small vertical hop. With nobody local to follow — a
	 * spectator, or a roster that has not arrived — it settles on the fire,
	 * which at least reads as a deliberate hold.
	 */
	private launchTarget(launch: Launch): { x: number; y: number } {
		const seat = this.seats.find((s) => s.id === launch.focusId);
		if (!seat) return { x: this.fireX, y: this.fireY };
		return {
			x: seat.targetX,
			y: seat.targetY - (this.camp?.config.playerHalfHeight ?? 0),
		};
	}

	private update(dt: number): void {
		if (this.launch) {
			// Clamped, not stopped: the move holds on its last frame until the
			// arena takes over, so there is never a gap where the lobby has
			// finished and nothing has replaced it.
			this.launch.elapsed = Math.min(
				this.launch.duration,
				this.launch.elapsed + dt,
			);
			// A seat that was still sliding when the host clicked keeps sliding,
			// so the target is re-read every frame rather than captured.
			this.frameCamera();
		}

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
			// Ease toward the server's position rather than snap to it: the
			// party re-spaces around the fire every time somebody joins, and a
			// roomful of characters teleporting a tile sideways is the same
			// event as a roomful sliding over to make room, told badly.
			const k = 1 - Math.exp(-RESEAT_RATE * dt);
			seat.x = lerp(seat.x, seat.targetX, k);
			seat.y = lerp(seat.y, seat.targetY, k);
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
			p.py = p.y;
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

		// No viewers: nobody here is carrying a lamp, and the camp is lit by the
		// fire alone. Same call the arena makes, so the night is the same night.
		if (this.world && this.fov) {
			this.fov.update(
				this.world,
				[],
				this.lights,
				{
					ambientTiles:
						this.camp?.config.visionAmbientTiles ?? FALLBACK_VISION.ambientTiles,
					lanternTiles:
						this.camp?.config.visionLanternTiles ?? FALLBACK_VISION.lanternTiles,
					coneDegrees:
						this.camp?.config.visionConeDegrees ?? FALLBACK_VISION.coneDegrees,
				},
				this.time,
				dt,
			);
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

		// The arena's pass order, to the letter — ground, bodies, overgrowth,
		// darkness, light. Anything reordered here is a difference the player
		// would see the instant the run starts.
		this.terrain.ground(ctx, world, camera, this.time);
		this.drawStanding();
		// Canopies and ferns close over whoever is standing behind them, exactly
		// as they do in the arena.
		this.terrain.overgrowth(ctx, world, camera, this.time);
		if (this.fov) this.darkness.draw(ctx, world, this.fov);
		this.darkness.drawFires(
			ctx,
			world.fires,
			this.tile,
			this.camp?.config.campfireLightTiles ?? FALLBACK_FIRE_TILES,
			this.time,
		);

		// Everything below is LIGHT, so it goes over the darkness rather than
		// under it — the same rule the arena's renderer follows for muzzle
		// flashes. The summon column washing over the body it is delivering is
		// the point: the character resolves inside the beam, not next to it.
		this.drawSummons();
		this.drawRings();
		this.drawParticles();

		ctx.restore();
		this.drawLabels();
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
				y: seat.y,
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

		const { x, y } = seat;
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

		// Squash-and-stretch, applied about the feet: the body arrives compressed
		// and springs back. Everything below is inside this transform, including
		// the crown, so the head and what sits on it move together.
		const settle = this.landingSquash(seat);
		if (settle !== 1) {
			ctx.translate(x, y);
			ctx.scale(1 + (1 - settle) * 0.75, settle);
			ctx.translate(-x, -y);
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
			// How much of the flame this body is facing: everyone on the near
			// side of the fire catches more of it than the ones behind it.
			const facing =
				0.55 +
				0.45 *
					clamp01((y - this.fireY) / (RING_TILES_Y * this.tile));
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

	/**
	 * Vertical scale of a body that has just landed: 1 when it is not settling.
	 *
	 * A damped cosine rather than an ease — the body overshoots, comes back
	 * past its height, and settles. A one-way ease reads as the sprite growing
	 * into place, which is a loading animation, not an impact.
	 */
	private landingSquash(seat: Seat): number {
		if (seat.phase !== "summoning") return 1;
		const since = seat.t - BODY_LANDED * SUMMON_TIME;
		if (since < 0 || since > LANDING_SETTLE) return 1;
		const k = since / LANDING_SETTLE;
		return 1 - 0.34 * Math.exp(-4.5 * k) * Math.cos(k * 9);
	}

	/**
	 * 0..1 opacity for anything that belongs to the LOBBY rather than to the
	 * world: gone by halfway through the launch, so the last third of the move
	 * is already just the game.
	 */
	private chromeAlpha(): number {
		if (!this.launch) return 1;
		return clamp01(1 - (this.launch.elapsed / this.launch.duration) * 2.4);
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

	/**
	 * The summoning column: a generated sprite, not a gradient.
	 *
	 * See server/tools/make_vfx.py. A canvas gradient was the one shape in this
	 * scene with no pixels in it — smooth against a screen where the ground is
	 * dithered and the fire is six flat colours — and it read as a filter laid
	 * over the game rather than as part of it.
	 *
	 * The sheet is anchored on its contact row, not its bottom edge, because the
	 * impact throws a shockwave into the rows below the ground line. It also
	 * carries the flash and the wave, so nothing here re-draws those.
	 *
	 * The art is greyscale and tinted per seat: the column that delivers a
	 * player is in their own colour, which is the same join the roster makes
	 * with its swatches. A single baked-in blue for everybody would make an
	 * arrival an event that happened NEAR somebody rather than TO them.
	 */
	private drawSummons(): void {
		const sheet = this.vfx?.summon;
		if (!sheet) return;
		const { ctx } = this;

		ctx.save();
		ctx.globalCompositeOperation = "lighter";
		for (const seat of this.seats) {
			if (seat.phase !== "summoning") continue;
			const { x, y } = seat;
			const frame = effectFrame(sheet, seat.t);
			ctx.drawImage(
				effectImage(sheet, seat.color),
				frame * sheet.frameWidth,
				0,
				sheet.frameWidth,
				sheet.frameHeight,
				Math.round(x - sheet.frameWidth / 2),
				Math.round(y - sheet.anchorY),
				sheet.frameWidth,
				sheet.frameHeight,
			);
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
			const x = Math.round(p.x);
			const y = Math.round(p.y);
			if (p.streak && p.py !== undefined) {
				// A falling mote can cross several pixels between frames. Drawing
				// the segment it travelled instead of the point it landed on is
				// the difference between rain and a dotted line.
				const from = Math.min(y, Math.round(p.py));
				const span = Math.max(p.size, Math.abs(y - Math.round(p.py)));
				ctx.fillRect(x, from, p.size, span);
				continue;
			}
			ctx.fillRect(x, y, p.size, p.size);
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
	 * Names, in screen space, on a card above the head.
	 *
	 * Departure Mono is a pixel face and is only crisp at multiples of 11 px, so
	 * labels are drawn at the real screen scale instead of being blown up with
	 * the rest of the scene.
	 *
	 * ABOVE, not below: the ring is elliptical, so the player at the front sits
	 * lower than the fire and a label under their feet lands on the seat of
	 * whoever is closer to the camera. Above the head the only thing a card can
	 * collide with is empty night.
	 *
	 * The card is the roster row from the panel on the left, drawn in pixels:
	 * inset panel fill, a hairline border, and a 2px bar in the player's colour
	 * down the leading edge. Same three parts, same order, so the list and the
	 * scene read as one thing — see components/lobby/PlayerRoster.tsx.
	 *
	 * They are LOBBY chrome, so they leave with the rest of it: the launch fades
	 * them out over its first half, and the arena draws its own labels in its
	 * own style. Carrying these across the handover would swap one nameplate for
	 * a different one on the same head, mid-move.
	 */
	private drawLabels(): void {
		const { ctx, camera } = this;
		const tone = palette();
		const chrome = this.chromeAlpha();
		if (chrome <= 0.01) return;
		// One design pixel, in device pixels. Every measurement below is a whole
		// multiple of it, so the card's edges land on the same grid as the font.
		const unit = Math.max(1, Math.round(this.dpr));
		const size = HUD_GRID * unit;
		const sheet = this.sprites.get(PLAYER_SHEET);
		// Departure Mono's metrics, in design pixels: caps rise 8 above the
		// baseline and descenders drop 3 below it. Measuring the card off those
		// rather than off the em box keeps the padding optically even.
		const capHeight = 8 * unit;
		const descent = 3 * unit;
		const padX = 4 * unit;
		// Descender space is reserved whether or not the name has one, so two
		// cards side by side are the same height and sit on the same line.
		const cardHeight = capHeight + descent + 5 * unit;

		ctx.save();
		ctx.setTransform(1, 0, 0, 1, 0, 0);
		ctx.font = hudFont(size);
		ctx.textAlign = "center";
		ctx.textBaseline = "alphabetic";

		for (const seat of this.seats) {
			const alpha = this.seatAlpha(seat) * chrome;
			if (alpha <= 0.05) continue;
			const { x, y } = seat;
			// Clear of the head, and of the crown when there is one. The body's
			// idle bob is deliberately NOT applied: a nameplate that bobs with the
			// character is a label that will not hold still to be read.
			// The crown is drawn 6px above the sprite, so a host needs the extra
			// room or their plate sits on it.
			const headTop =
				y - (sheet?.frameHeight ?? this.tile) - (seat.isHost ? 7 : 2);
			const cx = Math.round((x - camera.renderX) * camera.zoom);
			// The tip of the pointer touches the head; the card floats above it.
			const tipY = Math.round((headTop - camera.renderY) * camera.zoom);
			const cardBottom = tipY - 2 * unit;
			const cardTop = cardBottom - cardHeight;
			const baseline = cardBottom - descent - 2 * unit;

			const accent = 2 * unit;
			const textWidth =
				Math.ceil(ctx.measureText(seat.name).width / unit) * unit;
			const width = accent + padX * 2 + textWidth;
			const left = cx - Math.round(width / 2 / unit) * unit;

			ctx.globalAlpha = alpha * 0.88;
			ctx.fillStyle = tone.panelInset;
			ctx.fillRect(left, cardTop, width, cardHeight);

			// Border as four fills rather than a stroke: a 1px stroke straddles the
			// path and comes out as two half-lit rows on a canvas this size.
			ctx.globalAlpha = alpha * (seat.isLocal ? 0.9 : 0.5);
			ctx.fillStyle = tone.panelBorder;
			ctx.fillRect(left, cardTop, width, unit);
			ctx.fillRect(left, cardBottom - unit, width, unit);
			ctx.fillRect(left, cardTop, unit, cardHeight);
			ctx.fillRect(left + width - unit, cardTop, unit, cardHeight);

			// The colour bar, and the pointer below it. The pointer's first step
			// overlaps the bottom border so the two merge instead of leaving a
			// seam where the card ends.
			ctx.globalAlpha = alpha;
			ctx.fillStyle = seat.color;
			ctx.fillRect(left, cardTop, accent, cardHeight);
			ctx.globalAlpha = alpha * 0.88;
			ctx.fillStyle = tone.panelInset;
			for (let step = 0; step < 3; step++) {
				ctx.fillRect(
					cx - (2 - step) * unit,
					cardBottom - unit + step * unit,
					(5 - step * 2) * unit,
					unit,
				);
			}

			// Centred on the space BESIDE the colour bar rather than on the card,
			// so the bar does not push the name off its own plate. Snapped to the
			// design grid, since anything else puts the glyphs between pixels.
			const textX =
				Math.round((left + accent + padX + textWidth / 2) / unit) * unit;
			ctx.globalAlpha = alpha;
			ctx.fillStyle = tone.entity.labelShadow;
			ctx.fillText(seat.name, textX + unit, baseline + unit);
			ctx.fillStyle = seat.isLocal ? tone.ink : tone.inkMuted;
			ctx.fillText(seat.name, textX, baseline);
		}
		ctx.restore();
	}
}

/**
 * A clearing in the forest, for a scene with no server to ask — the title
 * screen. Mirrors what `server/app/camp.py` builds, closely enough that the
 * two look like the same place: open ground in the middle for the fire, a
 * ragged treeline closing in, and a solid wall of trunks at the border so the
 * camera never frames the end of the world.
 *
 * It stamps a FIRE tile like the real camp does, so the rest of this file can
 * read `world.fires` without caring which source it is drawing.
 */
function buildClearing(seed: number, tile: number): TileMap {
	const fx = Math.floor(MAP_TILES_W / 2);
	const fy = Math.floor(MAP_TILES_H / 2);
	const tiles: number[][] = [];

	for (let ty = 0; ty < MAP_TILES_H; ty++) {
		const row: number[] = [];
		for (let tx = 0; tx < MAP_TILES_W; tx++) {
			row.push(clearingTile(tx, ty, fx, fy, seed));
		}
		tiles.push(row);
	}
	tiles[fy][fx] = FIRE;

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

	const hearth = hearthDistance(tx, ty, cx, cy);
	// Nothing is allowed to stand in the hearth — see HEARTH_TILES.
	if (hearth < HEARTH_TILES) return FLOOR;

	// Squashed vertically to match the ellipse the seats sit on and the shape of
	// a landscape viewport — a circular clearing reads as a bulge on a wide screen.
	const dx = tx - cx;
	const dy = (ty - cy) * 1.45;
	const distance = Math.hypot(dx, dy);
	// A ragged edge, not a stamped circle.
	const edge = CLEARING_TILES + tileHash(tx, ty, seed, 7) * 1.8 - 0.9;

	if (distance < edge) {
		// A couple of boulders out on the clearing floor, well clear of the party.
		if (hearth > HEARTH_TILES + 1.5 && tileHash(tx, ty, seed, 8) > 0.94)
			return ROCK;
		return FLOOR;
	}

	// Density ramps with depth so the treeline thickens instead of starting solid.
	const depth = clamp01((distance - edge) / 5);
	if (tileHash(tx, ty, seed, 9) < 0.16 + depth * 0.66) return TREE;
	if (tileHash(tx, ty, seed, 10) < 0.05 + depth * 0.06) return ROCK;
	return FLOOR;
}

/**
 * Distance from the fire in tiles, on the same ellipse the seats sit on.
 *
 * Elliptical rather than circular because the seat ring is: measuring with a
 * circle would leave the players at the top and bottom of the ring standing in
 * scrub while the ones at the sides had room.
 */
function hearthDistance(tx: number, ty: number, cx: number, cy: number): number {
	const dx = tx - cx;
	const dy = (ty - cy) * (RING_TILES_X / RING_TILES_Y);
	return Math.hypot(dx, dy);
}

/** Symmetric ease. Slow out of the wide shot, slow into the landing. */
function easeInOut(t: number): number {
	return t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
}

/**
 * Even spacing round the ring, front seat (nearest the camera) first.
 *
 * Mirrors `camp.seat_position` on the server, and is only reached when there is
 * no server to mirror — see `contactPoint`.
 */
function seatAngle(index: number, total: number): number {
	return Math.PI / 2 + (index / Math.max(1, total)) * TAU;
}
