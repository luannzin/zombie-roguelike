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

/**
 * How much of its own size the skill tin flies at. See the note in the sprite
 * below — it is the one sprite in this animation that had to come DOWN.
 */
const SKILL_TIN_SCALE = 0.66;

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
          second animation beside it.

          ONE ZOOM FOR BOTH. The tin used to fly at 3x against a drop's 2x, so
          the same gesture delivered a 48px object for a skill and a 32px one
          for a rifle — and the tin, being the smaller sprite of the two, was
          the one that looked like the bigger prize. What the player is being
          shown is a PICKUP either way; a payout that arrives larger than
          everything else they collect all night reads as a different system
          announcing itself. Same size, same flight, different object.

          AND THE TIN IS THEN TRIMMED BACK BY A THIRD. Equal zoom made the two
          sprites equal in PIXELS and not on screen: a tin is 16x18 of solid
          cylinder where a loot icon is a small object with air around it, so
          at the same scale it still arrived as the biggest thing that has ever
          appeared over the player's head — parked there for half a second,
          covering their own body during the hold. The scale is on a wrapper
          rather than on `zoom` because `zoom` also sizes the label window off
          the manifest, and a fractional zoom would put the tin's picture on
          half a pixel. */}
      {fly.dest === 'skill' ? (
        <div style={{ transform: `scale(${SKILL_TIN_SCALE})` }}>
          <SkillCanIcon rarity={fly.rarity} frame={fly.frame} zoom={2} />
        </div>
      ) : (
        <LootIcon frame={fly.frame} zoom={2} />
      )}
    </div>
  );
}
