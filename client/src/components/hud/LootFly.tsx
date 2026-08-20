/**
 * Collect juice: the item lifts off the head and lands in the bag — or, for
 * the upgrade machine's payout, the tin lifts off the head and lands in the
 * skill tray.
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
import { SkillCanIcon } from './SkillCanIcon';

export interface LootFlyProps {
}

export function LootFly() {
  const flies = useSyncExternalStore(subscribeLootFlies, listLootFlies, listLootFlies);
  if (flies.length === 0) return null;

  return (
    <>
      {flies.map((fly) => (
        <LootFlySprite key={fly.id} fly={fly} />
      ))}
    </>
  );
}

function LootFlySprite({ fly }: { fly: LootFlySpec }) {
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
      {/* A skill arrives in a TIN and an item arrives as itself. Same flight,
          same hold over the head, different object in the hand — which is the
          whole reason the machine's payout reuses this and does not grow a
          second animation beside it. */}
      {fly.dest === 'skill' ? (
        <SkillCanIcon rarity={fly.rarity} frame={fly.frame} zoom={3} />
      ) : (
        <LootIcon frame={fly.frame} zoom={2} />
      )}
    </div>
  );
}
