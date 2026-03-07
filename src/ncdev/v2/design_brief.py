from __future__ import annotations

from ncdev.v2.models import (
    ColorSpec,
    ComponentDensitySpec,
    DesignBriefDoc,
    DesignDirection,
    DesignPackDoc,
    FeatureMapDoc,
    IconographySpec,
    LayoutSpec,
    MotionSpec,
    RadiusShadowSpec,
    ResearchPackDoc,
    SpacingSpec,
    TypographySpec,
)

_DIRECTION_PRESETS: dict[str, dict] = {
    "electric": {
        "typography": TypographySpec(
            font_display="Space Grotesk",
            font_body="Inter",
            font_mono="JetBrains Mono",
            scale={
                "xs": "0.75rem",
                "sm": "0.875rem",
                "base": "1rem",
                "lg": "1.125rem",
                "xl": "1.25rem",
                "2xl": "1.5rem",
                "3xl": "1.875rem",
                "4xl": "2.25rem",
                "5xl": "3rem",
            },
            line_heights={
                "tight": "1.25",
                "snug": "1.375",
                "normal": "1.5",
                "relaxed": "1.625",
            },
            weights={"normal": 400, "medium": 500, "semibold": 600, "bold": 700},
        ),
        "colors": ColorSpec(
            primary="#0f172a",
            secondary="#1e293b",
            accent="#14b8a6",
            highlight="#f97316",
            background="#0a0a0a",
            surface="#18181b",
            error="#ef4444",
            warning="#eab308",
            success="#22c55e",
            text_primary="#fafafa",
            text_secondary="#a1a1aa",
            text_inverse="#0a0a0a",
            border="#27272a",
        ),
        "spacing": SpacingSpec(
            unit="4px",
            scale={
                "0": "0",
                "1": "4px",
                "2": "8px",
                "3": "12px",
                "4": "16px",
                "5": "20px",
                "6": "24px",
                "8": "32px",
                "10": "40px",
                "12": "48px",
                "16": "64px",
                "20": "80px",
            },
        ),
        "radius_shadow": RadiusShadowSpec(
            radius={
                "none": "0",
                "sm": "6px",
                "md": "12px",
                "lg": "16px",
                "xl": "24px",
                "full": "9999px",
            },
            shadows={
                "sm": "0 1px 2px rgba(0,0,0,0.4)",
                "md": "0 4px 12px rgba(0,0,0,0.5)",
                "lg": "0 8px 24px rgba(0,0,0,0.6)",
                "glow": "0 0 20px rgba(20,184,166,0.3)",
            },
        ),
        "motion": MotionSpec(
            duration_fast="100ms",
            duration_normal="200ms",
            duration_slow="400ms",
            easing_default="cubic-bezier(0.4, 0, 0.2, 1)",
            easing_enter="cubic-bezier(0, 0, 0.2, 1)",
            easing_exit="cubic-bezier(0.4, 0, 1, 1)",
            rules=[
                "Use accent-colored glow transitions on interactive focus states.",
                "Entrance animations use scale-up from 0.95 with opacity fade.",
                "Page transitions use horizontal slide with 200ms duration.",
            ],
        ),
        "layout": LayoutSpec(
            breakpoints={"sm": "640px", "md": "768px", "lg": "1024px", "xl": "1280px", "2xl": "1536px"},
            max_content_width="1280px",
            grid_columns=12,
            shell_rules=[
                "Dark surface background with accent border highlights.",
                "Use asymmetric hero layouts on entry screens.",
                "Sidebar, when present, uses translucent glass-effect surface.",
            ],
        ),
        "component_density": ComponentDensitySpec(
            default_density="comfortable",
            input_height="40px",
            button_height="40px",
            rules=[
                "Buttons use accent fill with bold weight labels.",
                "Cards have lg radius with subtle glow shadow on hover.",
                "Tables use striped rows with surface/background alternation.",
            ],
        ),
        "iconography": IconographySpec(
            library="lucide-react",
            default_size="20px",
            stroke_width="1.5",
            rules=[
                "Icons inherit text color by default.",
                "Interactive icon buttons use accent color on hover.",
            ],
        ),
        "composition_rules": [
            "Avoid default left-nav plus blank-content shell unless the product truly needs it.",
            "Use asymmetry and intentional visual hierarchy on primary entry screens.",
            "Prefer themed surfaces and motion presets over ad hoc inline styling.",
            "Primary actions use accent color; destructive actions use error color.",
            "Empty states must include an icon, a message, and a primary action.",
        ],
    },
    "gloss": {
        "typography": TypographySpec(
            font_display="Plus Jakarta Sans",
            font_body="Plus Jakarta Sans",
            font_mono="Fira Code",
            scale={
                "xs": "0.75rem",
                "sm": "0.875rem",
                "base": "1rem",
                "lg": "1.125rem",
                "xl": "1.25rem",
                "2xl": "1.5rem",
                "3xl": "1.875rem",
                "4xl": "2.25rem",
                "5xl": "3rem",
            },
            line_heights={"tight": "1.25", "snug": "1.375", "normal": "1.5", "relaxed": "1.625"},
            weights={"normal": 400, "medium": 500, "semibold": 600, "bold": 700, "extrabold": 800},
        ),
        "colors": ColorSpec(
            primary="#1e293b",
            secondary="#334155",
            accent="#6366f1",
            highlight="#a78bfa",
            background="#ffffff",
            surface="#f1f5f9",
            error="#dc2626",
            warning="#f59e0b",
            success="#16a34a",
            text_primary="#0f172a",
            text_secondary="#64748b",
            text_inverse="#ffffff",
            border="#e2e8f0",
        ),
        "spacing": SpacingSpec(
            unit="4px",
            scale={
                "0": "0", "1": "4px", "2": "8px", "3": "12px", "4": "16px",
                "5": "20px", "6": "24px", "8": "32px", "10": "40px", "12": "48px",
                "16": "64px", "20": "80px",
            },
        ),
        "radius_shadow": RadiusShadowSpec(
            radius={"none": "0", "sm": "8px", "md": "12px", "lg": "16px", "xl": "24px", "full": "9999px"},
            shadows={
                "sm": "0 1px 3px rgba(0,0,0,0.08)",
                "md": "0 4px 12px rgba(0,0,0,0.1)",
                "lg": "0 10px 30px rgba(0,0,0,0.12)",
                "glass": "0 8px 32px rgba(99,102,241,0.08)",
            },
        ),
        "motion": MotionSpec(
            rules=[
                "Subtle scale on hover (1.02) with glass shadow bloom.",
                "Page transitions use fade with 180ms duration.",
                "Avoid jarring entrances; prefer opacity + translate-y(4px).",
            ],
        ),
        "layout": LayoutSpec(
            breakpoints={"sm": "640px", "md": "768px", "lg": "1024px", "xl": "1280px", "2xl": "1536px"},
            max_content_width="1200px",
            grid_columns=12,
            shell_rules=[
                "Light surfaces with layered card depth.",
                "Header uses frosted-glass backdrop blur.",
                "Content areas use generous padding and rounded containers.",
            ],
        ),
        "component_density": ComponentDensitySpec(
            default_density="comfortable",
            input_height="44px",
            button_height="44px",
            rules=[
                "Buttons use rounded-xl with soft shadow.",
                "Cards use glass shadow variant on hover.",
                "Inputs have subtle inner shadow for depth.",
            ],
        ),
        "iconography": IconographySpec(
            library="lucide-react",
            default_size="20px",
            stroke_width="1.75",
            rules=[
                "Icons use text-secondary by default, accent on active state.",
                "Use filled icon variants for navigation items.",
            ],
        ),
        "composition_rules": [
            "Emphasize depth through layered card surfaces and subtle shadows.",
            "Use frosted-glass effects for overlays and sticky headers.",
            "Primary entry screens use centered hero with generous whitespace.",
            "Maintain consistent border-radius across all interactive elements.",
            "Empty states use soft illustration style.",
        ],
    },
    "editorial": {
        "typography": TypographySpec(
            font_display="Playfair Display",
            font_body="Source Sans 3",
            font_mono="Source Code Pro",
            scale={
                "xs": "0.75rem",
                "sm": "0.875rem",
                "base": "1rem",
                "lg": "1.125rem",
                "xl": "1.25rem",
                "2xl": "1.5rem",
                "3xl": "2rem",
                "4xl": "2.5rem",
                "5xl": "3.5rem",
            },
            line_heights={"tight": "1.2", "snug": "1.35", "normal": "1.6", "relaxed": "1.75"},
            weights={"normal": 400, "medium": 500, "semibold": 600, "bold": 700},
        ),
        "colors": ColorSpec(
            primary="#1a1a2e",
            secondary="#16213e",
            accent="#e94560",
            highlight="#0f3460",
            background="#fefefe",
            surface="#f5f5f5",
            error="#b91c1c",
            warning="#d97706",
            success="#059669",
            text_primary="#1a1a2e",
            text_secondary="#6b7280",
            text_inverse="#fefefe",
            border="#d1d5db",
        ),
        "spacing": SpacingSpec(
            unit="4px",
            scale={
                "0": "0", "1": "4px", "2": "8px", "3": "12px", "4": "16px",
                "5": "20px", "6": "24px", "8": "32px", "10": "40px", "12": "48px",
                "16": "64px", "20": "80px",
            },
        ),
        "radius_shadow": RadiusShadowSpec(
            radius={"none": "0", "sm": "2px", "md": "4px", "lg": "8px", "xl": "12px", "full": "9999px"},
            shadows={
                "sm": "0 1px 2px rgba(0,0,0,0.06)",
                "md": "0 2px 8px rgba(0,0,0,0.08)",
                "lg": "0 4px 16px rgba(0,0,0,0.1)",
            },
        ),
        "motion": MotionSpec(
            duration_fast="120ms",
            duration_normal="250ms",
            duration_slow="500ms",
            rules=[
                "Minimal motion; prefer opacity fades over spatial transitions.",
                "Typography-driven hierarchy replaces motion-based emphasis.",
                "Scrolling content reveals with stagger delay per block.",
            ],
        ),
        "layout": LayoutSpec(
            breakpoints={"sm": "640px", "md": "768px", "lg": "1024px", "xl": "1280px", "2xl": "1536px"},
            max_content_width="960px",
            grid_columns=12,
            shell_rules=[
                "Narrow content column with generous margins.",
                "Use typographic scale contrast instead of borders to separate sections.",
                "Headers are minimal; navigation is secondary to content.",
            ],
        ),
        "component_density": ComponentDensitySpec(
            default_density="spacious",
            input_height="44px",
            button_height="44px",
            rules=[
                "Buttons are minimal with underline or outline variants preferred.",
                "Cards use minimal border with generous internal padding.",
                "Forms use generous vertical spacing between fields.",
            ],
        ),
        "iconography": IconographySpec(
            library="lucide-react",
            default_size="18px",
            stroke_width="1.5",
            rules=[
                "Icons are used sparingly; prefer text labels.",
                "When used, icons accompany labels rather than replacing them.",
            ],
        ),
        "composition_rules": [
            "Lead with typography scale contrast over color to create hierarchy.",
            "Use serif display font for headings, sans-serif for body.",
            "Minimize UI chrome; let content breathe with whitespace.",
            "Interactive elements are understated until hovered or focused.",
            "Empty states use editorial-style messaging with typographic emphasis.",
        ],
    },
}


def _resolve_direction(design_pack: DesignPackDoc) -> DesignDirection:
    for direction in design_pack.directions:
        if direction.name == design_pack.selected_direction:
            return direction
    if design_pack.directions:
        return design_pack.directions[0]
    return DesignDirection(
        name=design_pack.selected_direction or "electric",
        rationale="Default direction applied.",
        traits=["bold", "high-contrast"],
    )


def _apply_token_overrides(colors: ColorSpec, tokens: dict[str, str]) -> ColorSpec:
    mapping = {
        "color.primary": "primary",
        "color.secondary": "secondary",
        "color.accent": "accent",
        "color.highlight": "highlight",
        "color.background": "background",
        "color.surface": "surface",
        "color.error": "error",
        "color.warning": "warning",
        "color.success": "success",
        "color.text_primary": "text_primary",
        "color.text_secondary": "text_secondary",
        "color.text_inverse": "text_inverse",
        "color.border": "border",
    }
    overrides: dict[str, str] = {}
    for token_key, field_name in mapping.items():
        if token_key in tokens:
            overrides[field_name] = tokens[token_key]
    if overrides:
        return colors.model_copy(update=overrides)
    return colors


def generate_design_brief(
    design_pack: DesignPackDoc,
    feature_map: FeatureMapDoc | None = None,
    research_pack: ResearchPackDoc | None = None,
) -> DesignBriefDoc:
    direction = _resolve_direction(design_pack)
    preset = _DIRECTION_PRESETS.get(direction.name, _DIRECTION_PRESETS["electric"])

    typography: TypographySpec = preset["typography"]
    colors: ColorSpec = preset["colors"]
    spacing: SpacingSpec = preset["spacing"]
    radius_shadow: RadiusShadowSpec = preset["radius_shadow"]
    motion: MotionSpec = preset["motion"]
    layout: LayoutSpec = preset["layout"]
    component_density: ComponentDensitySpec = preset["component_density"]
    iconography: IconographySpec = preset["iconography"]
    composition_rules: list[str] = list(preset["composition_rules"])

    if "font.display" in design_pack.theme_tokens:
        typography = typography.model_copy(update={"font_display": design_pack.theme_tokens["font.display"]})
    if "font.body" in design_pack.theme_tokens:
        typography = typography.model_copy(update={"font_body": design_pack.theme_tokens["font.body"]})
    if "font.mono" in design_pack.theme_tokens:
        typography = typography.model_copy(update={"font_mono": design_pack.theme_tokens["font.mono"]})

    colors = _apply_token_overrides(colors, design_pack.theme_tokens)

    if "radius.card" in design_pack.theme_tokens:
        radius_shadow = radius_shadow.model_copy(
            update={"radius": {**radius_shadow.radius, "lg": design_pack.theme_tokens["radius.card"]}}
        )

    if design_pack.component_rules:
        composition_rules = list(design_pack.component_rules) + composition_rules

    if feature_map is not None and feature_map.ux_principles:
        for principle in feature_map.ux_principles:
            if principle not in composition_rules:
                composition_rules.append(principle)

    source_inputs = [f"design-pack:{design_pack.project_name}"]
    if feature_map is not None:
        source_inputs.append(f"feature-map:{feature_map.project_name}")
    if research_pack is not None:
        source_inputs.append(f"research-pack:{research_pack.project_name}")

    return DesignBriefDoc(
        generator="ncdev.v2.design_brief",
        source_inputs=source_inputs,
        project_name=design_pack.project_name,
        direction_name=direction.name,
        direction_rationale=direction.rationale,
        direction_traits=list(direction.traits),
        typography=typography,
        colors=colors,
        spacing=spacing,
        radius_shadow=radius_shadow,
        motion=motion,
        layout=layout,
        component_density=component_density,
        iconography=iconography,
        composition_rules=composition_rules,
    )
