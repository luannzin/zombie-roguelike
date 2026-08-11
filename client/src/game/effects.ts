/**
 * Purely visual, short-lived effects. Holds no authoritative state — safe to
 * drop or replay at will.
 */

export interface Tracer {
  x: number;
  y: number;
  dx: number;
  dy: number;
  dist: number;
  color: string;
  age: number;
  life: number;
}

export interface Flash {
  x: number;
  y: number;
  dx: number;
  dy: number;
  age: number;
  life: number;
}

export interface Impact {
  x: number;
  y: number;
  hit: boolean;
  age: number;
  life: number;
}

export class Effects {
  tracers: Tracer[] = [];
  flashes: Flash[] = [];
  impacts: Impact[] = [];

  spawnShot(
    x: number,
    y: number,
    dx: number,
    dy: number,
    dist: number,
    color: string,
    hit: boolean,
  ): void {
    this.tracers.push({ x, y, dx, dy, dist, color, age: 0, life: 0.09 });
    this.flashes.push({ x, y, dx, dy, age: 0, life: 0.06 });
    this.impacts.push({
      x: x + dx * dist,
      y: y + dy * dist,
      hit,
      age: 0,
      life: hit ? 0.25 : 0.15,
    });
  }

  update(dt: number): void {
    this.tracers = advance(this.tracers, dt);
    this.flashes = advance(this.flashes, dt);
    this.impacts = advance(this.impacts, dt);
  }
}

function advance<T extends { age: number; life: number }>(items: T[], dt: number): T[] {
  const out: T[] = [];
  for (const item of items) {
    item.age += dt;
    if (item.age < item.life) out.push(item);
  }
  return out;
}
