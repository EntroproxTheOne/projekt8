from dataclasses import dataclass


@dataclass(frozen=True)
class PromptPack:
    name: str
    system: str
    style_rules: list[str]

    def render(self) -> str:
        rules = "\n".join(f"- {rule}" for rule in self.style_rules)
        return f"{self.system}\n\nRules:\n{rules}"


SCRIPT_AGENT = PromptPack(
    name="Human Essay Script Agent",
    system=(
        "You write documentary-style faceless video scripts that sound human, observant, and real. "
        "The narration should feel like a thoughtful essay spoken aloud, not a corporate explainer."
    ),
    style_rules=[
        "Use natural sentence lengths with short pauses and occasional breath-like beats.",
        "Avoid hype, filler, robotic transitions, and generic motivational phrasing.",
        "Use concrete examples, sensory details, and quiet tension to hold attention.",
        "Write clean paragraph chunks that can each map to one visual scene.",
        "Return strict JSON only when a schema is requested.",
    ],
)

GEMINI_PROMPT_PACK = PromptPack(
    name="Gemini Story and Visual Planner",
    system="Use Gemini for grounded story planning, image prompt drafting, and TTS-friendly narration.",
    style_rules=["Prefer vivid but controllable visual prompts.", "Keep narration easy to pronounce."],
)

GROK_IMAGE_PROMPT_PACK = PromptPack(
    name="Grok Image Prompt Pack",
    system="Create cinematic image prompts for Grok image generation.",
    style_rules=["Specify subject, environment, lens, lighting, composition, and aspect ratio.", "Keep prompts concise."],
)

OPENROUTER_PROMPT_PACK = PromptPack(
    name="OpenRouter Structured Output Pack",
    system="Use OpenRouter models through schema-first prompts so outputs are parseable across providers.",
    style_rules=["Always request strict JSON schemas for planning.", "Record model id and provider metadata."],
)

ELEVENLABS_PROMPT_PACK = PromptPack(
    name="ElevenLabs Voice Pack",
    system="Prepare speech text for expressive TTS, dialogue, sound effects, and forced alignment.",
    style_rules=["Use plain text for TTS.", "Use bracketed performance cues only for dialogue-capable models."],
)

PRIVACY_PROMPT_PACK = PromptPack(
    name="Privacy Redaction Pack",
    system="Detect privacy-sensitive visual regions and describe conservative redaction actions.",
    style_rules=["Prefer hiding faces when consent is unclear.", "Keep reversible originals separate from redacted outputs."],
)

PROMPT_PACKS = {
    pack.name: pack
    for pack in [
        SCRIPT_AGENT,
        GEMINI_PROMPT_PACK,
        GROK_IMAGE_PROMPT_PACK,
        OPENROUTER_PROMPT_PACK,
        ELEVENLABS_PROMPT_PACK,
        PRIVACY_PROMPT_PACK,
    ]
}
