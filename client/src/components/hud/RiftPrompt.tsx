/**
 * Interact prompt on an extraction pad. One use of `Tooltip`.
 *
 * FOUR THINGS THE BUTTON CAN BE SAYING, and they are not interchangeable: wake
 * the platform, wait (another pad is already running), TIP THE BAG INTO it, or
 * CALL THE PICKUP. Loading past the quota used to be a fifth line of its own
 * ("sobrecarregar"); it is not a fifth ACT — E tips the whole bag in on either
 * side of the bill — so the overshoot is reported by the count, not by a
 * second sentence the player has to notice changed.
 *
 * THE LOAD LINE NAMES THE VERB THE BODY PERFORMS, not the machine's job.
 * "Carregar a plataforma" described what the pad ends up with; what E actually
 * starts is the player taking the pack off their shoulders and turning it
 * upside down, and the whole reason that pour is a ceremony is that the party
 * watches THEIR bag being emptied. The coin count beside the line is the same
 * number the quest row carries — how much of tonight's bill this pad has been
 * paid — so the sentence says what is being given and the badge says how far
 * it goes.
 *
 * THAT LAST ONE IS THE MOST EXPENSIVE PRESS IN THE GAME and the line has to
 * say so before it happens, not after. Everything up to it is quiet and
 * reversible; that one turns four green lamps red, starts a siren in a black
 * forest, and puts every creature on the map on hunt for thirteen seconds
 * while the party stands next to the pad waiting for aircraft. So it is the
 * one prompt in the game drawn in the danger tone, and it names the
 * consequence rather than the verb.
 *
 * Mounted only while in reach.
 */

import type { HudRiftPrompt } from "../../game/hud-store";
import { QuestCount } from "./QuestCount";
import { Tooltip, TooltipKey } from "./Tooltip";

export interface RiftPromptProps {
	prompt: HudRiftPrompt | null;
}

export function RiftPrompt({ prompt }: RiftPromptProps) {
	if (!prompt) return null;

	if (prompt.mode === "open") {
		return (
			<Tooltip anchor="rift">
				Aperte <TooltipKey>E</TooltipKey> para ligar a plataforma
			</Tooltip>
		);
	}

	if (prompt.mode === "busy") {
		return (
			<Tooltip anchor="rift">
				<span className="text-hp-low">Outra plataforma está ligada</span>
			</Tooltip>
		);
	}

	const count = <QuestCount have={prompt.have} need={prompt.need} gold />;

	if (prompt.mode === "close") {
		return (
			<Tooltip anchor="rift" end={count}>
				Aperte <TooltipKey>E</TooltipKey> para chamar a extração
			</Tooltip>
		);
	}

	if (prompt.empty) {
		return (
			<Tooltip anchor="rift" end={count}>
				<span className="text-hp-low">Inventário vazio</span>
			</Tooltip>
		);
	}

	return (
		<Tooltip anchor="rift" end={count}>
			Aperte <TooltipKey>E</TooltipKey> para despejar itens da mochila
		</Tooltip>
	);
}
