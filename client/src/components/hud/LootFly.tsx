/**
 * Collect juice: the item lifts off the head and lands in the bag.
 *
 * Membership comes from `loot-flies` (spawn / land only). Pose is a
 * transform written in rAF, same idea as a world tooltip.
 */

import { useEffect, useRef, useSyncExternalStore } from 'react';
import {
  listLootFlies,
  readLootFlyPose,
  subscribeLootFlies,
  type LootFlySpec,
} from '../../game/loot-flies';
import { LootIcon } from './LootIcon';

export interface LootFlyProps {
  lootFrames: number;
}

export function LootFly({ lootFrames }: LootFlyProps) {
  const flies = useSyncExternalStore(subscribeLootFlies, listLootFlies, listLootFlies);
  if (flies.length === 0) return null;

  return (
    <>
      {flies.map((fly) => (
        <LootFlySprite key={fly.id} fly={fly} lootFrames={lootFrames} />
      ))}
    </>
  );
}

function LootFlySprite({ fly, lootFrames }: { fly: LootFlySpec; lootFrames: number }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let raf = 0;
    const tick = () => {
      const pose = readLootFlyPose(fly.id);
      if (pose) {
        el.style.transform = `translate(${pose.x}px, ${pose.y}px) translate(-50%, -50%) rotate(${pose.rotate}deg) scale(${pose.scale})`;
        el.style.opacity = String(pose.alpha);
        el.style.visibility = 'visible';
      } else {
        el.style.visibility = 'hidden';
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [fly.id]);

  return (
    <div
      ref={ref}
      className="pointer-events-none fixed top-0 left-0"
      style={{ visibility: 'hidden' }}
      aria-hidden="true"
    >
      <LootIcon frame={fly.frame} frames={lootFrames} zoom={2} />
    </div>
  );
}
