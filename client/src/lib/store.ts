/**
 * Minimal external store, shaped for React's `useSyncExternalStore`.
 *
 * The game loop runs outside React and pushes state in; components subscribe.
 * Nothing here imports React, so the game core stays framework-free — rooms,
 * lobby and settings state can reuse this later.
 */

export type Unsubscribe = () => void;

export class Store<T> {
  private current: T;
  private readonly listeners = new Set<() => void>();

  constructor(initial: T) {
    this.current = initial;
  }

  /** Bound so it can be passed straight to useSyncExternalStore. */
  subscribe = (listener: () => void): Unsubscribe => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  getSnapshot = (): T => this.current;

  set(next: T): void {
    if (Object.is(next, this.current)) return;
    this.current = next;
    for (const listener of this.listeners) listener();
  }

  update(producer: (previous: T) => T): void {
    this.set(producer(this.current));
  }
}
