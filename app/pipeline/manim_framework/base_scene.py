"""
app/pipeline/manim_framework/base_scene.py
-------------------------------------------
ChemistryScene: Manim base class with pre-built effect renderers.

Every effect keyword in the catalog maps to a `_render_<KEYWORD>` method here.
The generated scene file calls `self.play_effect(keyword, params, duration)` —
it never touches raw Manim primitives directly, so there is no LLM hallucination
surface in the rendering layer.

Video format: 1080x1920 (9:16 vertical, TikTok/Shorts style).
"""

from __future__ import annotations

import numpy as np
from manim import (
    UP, DOWN, LEFT, RIGHT, ORIGIN, IN, OUT,
    WHITE, BLACK, GRAY, YELLOW, RED, ORANGE, GREEN, BLUE, PURPLE, TEAL,
    PI,
    Scene, VGroup, Group,
    Text, MathTex, Tex,
    Circle, Rectangle, Square, Line, DashedLine, Arrow,
    Dot, Triangle,
    NumberLine,
    SurroundingRectangle,
    FadeIn, FadeOut, Write, Create, Transform, TransformMatchingTex,
    MoveToTarget,
    AnimationGroup, LaggedStart,
    config as manim_config,
)

# ── Colour palette ─────────────────────────────────────────────────────────────
BG_COLOR      = "#0F1117"
FORMULA_BLUE  = "#58C4DD"
GOLD          = "#FFD700"
ACID_RED      = "#FF4444"
BASE_BLUE     = "#4488FF"
NEUTRAL_GREEN = "#44CC66"

# Element colour lookup used by atom / bond renderers
ELEMENT_COLORS = {
    "H":  "#FFFFFF",
    "O":  "#FF4444",
    "N":  "#4444FF",
    "C":  "#888888",
    "Cl": "#44DD44",
    "Na": "#FF8800",
    "S":  "#FFFF00",
    "P":  "#FF6600",
}


def _element_color(symbol: str) -> str:
    return ELEMENT_COLORS.get(symbol, FORMULA_BLUE)


class ChemistryScene(Scene):
    """
    Base scene class for AI-generated chemistry videos.
    Configured for 9:16 vertical portrait video.
    """

    def setup(self) -> None:
        self.camera.background_color = BG_COLOR

    # ── Dispatcher ─────────────────────────────────────────────────────────────

    def play_effect(self, effect: str, params: dict, duration: float) -> None:
        """
        Dispatch to the matching _render_<EFFECT> method.
        Clears the screen first, then renders, then waits for any
        remaining time in duration.
        """
        # Fade out everything currently on screen
        if self.mobjects:
            self.play(FadeOut(*self.mobjects, run_time=0.4))

        renderer = getattr(self, f"_render_{effect}", None)
        if renderer is None:
            raise ValueError(
                f"No renderer found for effect '{effect}'. "
                f"Check effects_catalog.py for valid keywords."
            )
        renderer(params, duration)

    # ── Structural ─────────────────────────────────────────────────────────────

    def _render_TITLE_CARD(self, params: dict, duration: float) -> None:
        color = params.get("color", FORMULA_BLUE)
        title = Text(params["title"], font_size=54, color=color, weight="BOLD")
        subtitle_text = params.get("subtitle", "")

        if subtitle_text:
            subtitle = Text(subtitle_text, font_size=30, color=WHITE)
            group = VGroup(title, subtitle).arrange(DOWN, buff=0.55)
        else:
            group = title

        group.move_to(ORIGIN)

        self.play(Write(title), run_time=1.2)
        if subtitle_text:
            self.play(FadeIn(subtitle, shift=UP * 0.2), run_time=0.6)
        self.wait(max(duration - 2.0, 0.3))

    def _render_SECTION_TITLE(self, params: dict, duration: float) -> None:
        color = params.get("color", WHITE)
        text = Text(params["text"], font_size=46, color=color, weight="BOLD")
        underline = Line(LEFT * 2.8, RIGHT * 2.8, color=color, stroke_width=2)
        underline.next_to(text, DOWN, buff=0.12)
        group = VGroup(text, underline).move_to(ORIGIN)

        self.play(Write(text), run_time=0.8)
        self.play(Create(underline), run_time=0.4)
        self.wait(max(duration - 1.5, 0.2))

    def _render_CONCLUSION_CARD(self, params: dict, duration: float) -> None:
        title_text = params.get("title", "Key Takeaways")
        bullets: list[str] = params["bullets"]

        title = Text(title_text, font_size=38, color=GOLD, weight="BOLD")
        underline = Line(LEFT * 2.5, RIGHT * 2.5, color=GOLD, stroke_width=2)

        header = VGroup(title, underline).arrange(DOWN, buff=0.15)
        header.shift(UP * (2.5 + (len(bullets) - 2) * 0.3))

        bullet_objs = [
            Text(f"• {b}", font_size=26, color=WHITE)
            for b in bullets
        ]
        bullet_group = VGroup(*bullet_objs).arrange(DOWN, buff=0.38, aligned_edge=LEFT)
        bullet_group.next_to(header, DOWN, buff=0.4)

        self.play(Write(title), Create(underline), run_time=0.9)
        for b in bullet_objs:
            self.play(FadeIn(b, shift=RIGHT * 0.25), run_time=0.45)
        self.wait(max(duration - len(bullets) * 0.45 - 1.5, 0.3))

    # ── Text / explanation ─────────────────────────────────────────────────────

    def _render_TEXT_REVEAL(self, params: dict, duration: float) -> None:
        font_size = params.get("font_size", 34)
        lines: list[str] = params["lines"]
        texts = [Text(line, font_size=font_size, color=WHITE) for line in lines]
        group = VGroup(*texts).arrange(DOWN, buff=0.45, aligned_edge=LEFT)
        group.move_to(ORIGIN)

        per_line = max((duration - 0.5) / len(lines), 0.5)
        for t in texts:
            self.play(FadeIn(t, shift=RIGHT * 0.25), run_time=min(per_line * 0.55, 1.0))
            self.wait(min(per_line * 0.45, 1.5))

    def _render_HIGHLIGHT_BOX(self, params: dict, duration: float) -> None:
        color = params.get("color", GOLD)
        label_text = params.get("label", "")
        box_text = Text(params["text"], font_size=32, color=WHITE)
        box = SurroundingRectangle(box_text, color=color, buff=0.3, corner_radius=0.15)
        group = VGroup(box, box_text).move_to(ORIGIN)

        if label_text:
            label = Text(label_text, font_size=24, color=color)
            label.next_to(group, UP, buff=0.35)
            self.play(FadeIn(label), run_time=0.5)

        self.play(Create(box), Write(box_text), run_time=1.1)
        self.wait(max(duration - 1.8, 0.3))

    # ── Formula / chemistry ────────────────────────────────────────────────────

    def _render_FORMULA_DISPLAY(self, params: dict, duration: float) -> None:
        color = params.get("color", FORMULA_BLUE)
        scale = float(params.get("scale", 1.0))
        formulas_raw: list[str] = params["formulas"]
        formulas = [MathTex(f, color=color).scale(scale) for f in formulas_raw]

        group = VGroup(*formulas).arrange(DOWN, buff=0.6)
        # Scale down if too tall for frame
        if group.height > 7.0:
            group.scale(7.0 / group.height)
        group.move_to(ORIGIN)

        per = max((duration - 0.3) / len(formulas), 0.5)
        for f in formulas:
            self.play(Write(f), run_time=min(per * 0.65, 1.8))
            self.wait(min(per * 0.35, 1.0))

    def _render_FORMULA_TRANSFORM(self, params: dict, duration: float) -> None:
        label_text = params.get("label", "")
        from_tex = MathTex(params["from_formula"], color=FORMULA_BLUE, font_size=52)
        to_tex   = MathTex(params["to_formula"],   color=GOLD,         font_size=52)
        from_tex.move_to(ORIGIN)
        to_tex.move_to(ORIGIN)

        if label_text:
            lbl = Text(label_text, font_size=26, color=GRAY).shift(UP * 2.2)
            self.play(FadeIn(lbl), run_time=0.4)

        self.play(Write(from_tex), run_time=1.2)
        self.wait(0.9)
        self.play(TransformMatchingTex(from_tex, to_tex), run_time=1.8)
        self.wait(max(duration - 4.5, 0.3))

    def _render_EQUATION_STEP(self, params: dict, duration: float) -> None:
        color = params.get("color", WHITE)
        steps_raw: list[str] = params["steps"]
        steps = [MathTex(s, color=color) for s in steps_raw]

        group = VGroup(*steps).arrange(DOWN, buff=0.5)
        if group.height > 7.2:
            group.scale(7.2 / group.height)
        group.move_to(ORIGIN)

        per = max((duration - 0.4) / len(steps), 0.6)
        for step in steps:
            self.play(Write(step), run_time=min(per * 0.7, 2.2))
            self.wait(min(per * 0.3, 1.2))

    # ── Molecular diagrams ────────────────────────────────────────────────────

    def _render_ATOM_DIAGRAM(self, params: dict, duration: float) -> None:
        show_electrons = params.get("show_electrons", True)
        atoms_data: list[dict] = params["atoms"]

        atom_objs = []
        for ad in atoms_data:
            sym = ad["symbol"]
            col = ad.get("color", _element_color(sym))
            circle = Circle(radius=0.58, color=col, fill_color=col, fill_opacity=0.18)
            label = Text(sym, font_size=34, weight="BOLD", color=col)
            atom_objs.append(VGroup(circle, label))

        group = VGroup(*atom_objs).arrange(RIGHT, buff=1.8).move_to(ORIGIN)
        self.play(LaggedStart(*[FadeIn(a) for a in atom_objs], lag_ratio=0.4), run_time=1.0)

        if show_electrons:
            dots = VGroup()
            for atom_obj in atom_objs:
                center = atom_obj.get_center()
                for angle in [0, PI / 2, PI, 3 * PI / 2]:
                    d = Dot(radius=0.07, color=YELLOW)
                    d.move_to(center + 0.88 * np.array([np.cos(angle), np.sin(angle), 0]))
                    dots.add(d)
            self.play(FadeIn(dots), run_time=0.7)

        self.wait(max(duration - 2.0, 0.3))

    def _render_BOND_FORMATION(self, params: dict, duration: float) -> None:
        atom_a = params["atom_a"]
        atom_b = params["atom_b"]
        bond_type: str = params.get("bond_type", "single")
        label_text: str = params.get("label", "")

        def _atom(sym: str) -> VGroup:
            col = _element_color(sym)
            c = Circle(radius=0.55, color=col, fill_color=col, fill_opacity=0.22)
            t = Text(sym, font_size=32, weight="BOLD", color=col)
            return VGroup(c, t)

        a = _atom(atom_a).move_to(LEFT * 2.8)
        b = _atom(atom_b).move_to(RIGHT * 2.8)

        self.play(FadeIn(a), FadeIn(b), run_time=0.8)
        self.play(
            a.animate.move_to(LEFT * 0.8),
            b.animate.move_to(RIGHT * 0.8),
            run_time=1.4,
        )

        if bond_type == "double":
            bond = VGroup(
                Line(LEFT * 0.25 + UP * 0.12,  RIGHT * 0.25 + UP * 0.12,  color=WHITE, stroke_width=5),
                Line(LEFT * 0.25 + DOWN * 0.12, RIGHT * 0.25 + DOWN * 0.12, color=WHITE, stroke_width=5),
            )
        elif bond_type == "ionic":
            bond = DashedLine(LEFT * 0.3, RIGHT * 0.3, color=YELLOW, stroke_width=4)
        else:  # single
            bond = Line(LEFT * 0.25, RIGHT * 0.25, color=WHITE, stroke_width=6)

        self.play(Create(bond), run_time=0.8)

        if label_text:
            lbl = Text(label_text, font_size=24, color=GOLD)
            lbl.next_to(bond, DOWN, buff=0.7)
            self.play(FadeIn(lbl), run_time=0.4)

        self.wait(max(duration - 4.0, 0.3))

    def _render_MOLECULE_LABEL(self, params: dict, duration: float) -> None:
        color = params.get("color", FORMULA_BLUE)
        name_text = Text(params["name"], font_size=42, weight="BOLD", color=WHITE)
        formula_tex = MathTex(params["formula"], font_size=58, color=color)
        group = VGroup(name_text, formula_tex).arrange(DOWN, buff=0.5).move_to(ORIGIN)

        self.play(Write(name_text), run_time=0.8)
        self.play(Write(formula_tex), run_time=1.2)
        self.wait(max(duration - 2.3, 0.3))

    def _render_ELECTRON_TRANSFER(self, params: dict, duration: float) -> None:
        from_atom = params["from_atom"]
        to_atom   = params["to_atom"]
        electron_color = params.get("electron_color", YELLOW)

        def _atom(sym: str) -> VGroup:
            col = _element_color(sym)
            c = Circle(radius=0.55, color=col, fill_color=col, fill_opacity=0.22)
            t = Text(sym, font_size=30, weight="BOLD", color=col)
            return VGroup(c, t)

        a = _atom(from_atom).move_to(LEFT * 2.2)
        b = _atom(to_atom).move_to(RIGHT * 2.2)
        electron = Dot(radius=0.13, color=electron_color).move_to(LEFT * 2.2 + UP * 0.65)

        self.play(FadeIn(a), FadeIn(b), run_time=0.7)
        self.play(FadeIn(electron), run_time=0.4)
        self.play(electron.animate.move_to(RIGHT * 2.2 + UP * 0.65), run_time=2.2)

        # Flash on arrival
        self.play(electron.animate.scale(1.8), run_time=0.2)
        self.play(electron.animate.scale(1 / 1.8), run_time=0.2)

        self.wait(max(duration - 4.0, 0.3))

    # ── Scale / comparison ─────────────────────────────────────────────────────

    def _render_PH_SCALE(self, params: dict, duration: float) -> None:
        highlight_ph = params.get("highlight_ph", None)
        show_examples = params.get("show_examples", True)

        bar_w = 6.2
        seg_count = 14
        seg_w = bar_w / seg_count

        # Colour gradient: red(0) → orange → yellow → green(7) → teal → blue → purple(14)
        gradient = [
            "#FF0000", "#FF2200", "#FF4400", "#FF6600",
            "#FFAA00", "#FFDD00", "#00CC44",
            "#00AAAA", "#0088CC", "#0066FF",
            "#3344FF", "#5522FF", "#7700EE", "#9900BB",
        ]

        segments = VGroup()
        for i, col in enumerate(gradient):
            seg = Rectangle(
                width=seg_w, height=0.55,
                fill_color=col, fill_opacity=0.95, stroke_width=0,
            )
            seg.move_to(LEFT * (bar_w / 2 - seg_w / 2) + RIGHT * i * seg_w)
            segments.add(seg)
        segments.move_to(ORIGIN)

        # Tick labels at 0, 7, 14
        def _tick(val: int) -> VGroup:
            seg = segments[val if val < seg_count else seg_count - 1]
            tick = Line(UP * 0.28, DOWN * 0.28, color=WHITE, stroke_width=2)
            tick.move_to(seg.get_center())
            lbl = Text(str(val), font_size=20, color=WHITE)
            lbl.next_to(tick, DOWN, buff=0.12)
            return VGroup(tick, lbl)

        ticks = VGroup(_tick(0), _tick(7), _tick(13))  # 13 ≈ 14 position

        title = Text("pH Scale", font_size=36, color=WHITE, weight="BOLD").shift(UP * 2.3)
        acid_lbl = Text("Acid", font_size=22, color=ACID_RED).shift(LEFT * 2.6 + DOWN * 0.9)
        neutral_lbl = Text("Neutral", font_size=22, color=NEUTRAL_GREEN).shift(DOWN * 0.9)
        base_lbl = Text("Base", font_size=22, color=BASE_BLUE).shift(RIGHT * 2.6 + DOWN * 0.9)

        self.play(Write(title), run_time=0.7)
        self.play(Create(segments), run_time=1.4)
        self.play(FadeIn(ticks), FadeIn(acid_lbl), FadeIn(neutral_lbl), FadeIn(base_lbl))

        if highlight_ph is not None:
            ratio = highlight_ph / 14.0
            x_pos = -bar_w / 2 + ratio * bar_w
            marker = Triangle(fill_color=GOLD, fill_opacity=1).scale(0.18)
            marker.move_to(np.array([x_pos, 0.45, 0]))
            ph_lbl = Text(f"pH {highlight_ph}", color=GOLD, font_size=26)
            ph_lbl.next_to(marker, UP, buff=0.12)
            self.play(FadeIn(marker), Write(ph_lbl), run_time=0.8)

        if show_examples:
            examples = Text(
                "Lemon juice pH≈2  |  Blood pH≈7.4  |  Bleach pH≈13",
                font_size=19, color=GRAY,
            ).shift(DOWN * 1.6)
            self.play(FadeIn(examples), run_time=0.6)

        self.wait(max(duration - 4.5, 0.3))

    def _render_COMPARISON_TABLE(self, params: dict, duration: float) -> None:
        left_header  = params["left_header"]
        right_header = params["right_header"]
        rows: list[list[str]] = params["rows"]
        title_text = params.get("title", "")

        divider = Line(UP * 3.8, DOWN * 3.8, color=GRAY, stroke_width=1.5)
        l_hdr = Text(left_header,  font_size=28, color=FORMULA_BLUE, weight="BOLD")
        r_hdr = Text(right_header, font_size=28, color=GOLD,         weight="BOLD")
        l_hdr.move_to(LEFT * 2.6 + UP * 2.8)
        r_hdr.move_to(RIGHT * 2.6 + UP * 2.8)

        header_underline = Line(LEFT * 5, RIGHT * 5, color=GRAY, stroke_width=1)
        header_underline.shift(UP * 2.4)

        anim_list = [Create(divider), Write(l_hdr), Write(r_hdr), Create(header_underline)]
        if title_text:
            t = Text(title_text, font_size=30, color=WHITE, weight="BOLD").shift(UP * 3.6)
            anim_list.append(Write(t))

        self.play(*anim_list, run_time=1.0)

        for i, row in enumerate(rows):
            y = 2.0 - i * 0.75
            lt = Text(row[0], font_size=22, color=WHITE).move_to(LEFT * 2.6 + UP * y)
            rt = Text(row[1], font_size=22, color=WHITE).move_to(RIGHT * 2.6 + UP * y)
            self.play(FadeIn(lt), FadeIn(rt), run_time=0.45)

        self.wait(max(duration - len(rows) * 0.45 - 1.5, 0.3))

    def _render_NUMBER_LINE(self, params: dict, duration: float) -> None:
        color = params.get("color", FORMULA_BLUE)
        min_val = float(params["min_val"])
        max_val = float(params["max_val"])
        labels: list[dict] = params["labels"]

        step = (max_val - min_val) / 7
        nl = NumberLine(
            x_range=[min_val, max_val, step],
            length=6.5,
            include_numbers=False,
            color=color,
        ).move_to(ORIGIN)

        self.play(Create(nl), run_time=1.4)

        for lbl_data in labels:
            val = float(lbl_data["value"])
            txt = lbl_data["text"]
            dot = Dot(nl.n2p(val), color=GOLD, radius=0.10)
            lbl = Text(txt, font_size=20, color=WHITE)
            lbl.next_to(dot, UP, buff=0.22)
            self.play(FadeIn(dot), Write(lbl), run_time=0.55)

        self.wait(max(duration - 2.2, 0.3))

    # ── Process / flow ─────────────────────────────────────────────────────────

    def _render_ARROW_DIAGRAM(self, params: dict, duration: float) -> None:
        steps: list[str] = params["steps"]
        box_color   = params.get("color", FORMULA_BLUE)
        arrow_color = params.get("arrow_color", WHITE)

        boxes = []
        for step in steps:
            txt = Text(step, font_size=26, color=WHITE)
            box = SurroundingRectangle(txt, color=box_color, buff=0.22, corner_radius=0.1)
            boxes.append(VGroup(box, txt))

        # Portrait layout: vertical flow
        group = VGroup(*boxes).arrange(DOWN, buff=0.7).move_to(ORIGIN)
        if group.height > 7.5:
            group.scale(7.5 / group.height)

        arrows = [
            Arrow(
                boxes[i].get_bottom() + DOWN * 0.05,
                boxes[i + 1].get_top() + UP * 0.05,
                buff=0.0,
                color=arrow_color,
                stroke_width=3,
                max_tip_length_to_length_ratio=0.2,
            )
            for i in range(len(boxes) - 1)
        ]

        for i, box in enumerate(boxes):
            self.play(Create(box), run_time=0.65)
            if i < len(arrows):
                self.play(Create(arrows[i]), run_time=0.35)

        self.wait(max(duration - len(boxes) * 1.0 - 0.5, 0.3))

    def _render_PROS_CONS(self, params: dict, duration: float) -> None:
        l_title  = params["left_title"]
        l_items: list[str] = params["left_items"]
        r_title  = params["right_title"]
        r_items: list[str] = params["right_items"]

        divider = Line(UP * 3.8, DOWN * 3.8, color=GRAY, stroke_width=1.5)
        l_hdr = Text(l_title, font_size=26, color=FORMULA_BLUE, weight="BOLD").move_to(LEFT * 2.6 + UP * 2.9)
        r_hdr = Text(r_title, font_size=26, color=GOLD,         weight="BOLD").move_to(RIGHT * 2.6 + UP * 2.9)

        self.play(Create(divider), Write(l_hdr), Write(r_hdr), run_time=0.9)

        n = max(len(l_items), len(r_items))
        for i in range(n):
            y = 2.2 - i * 0.75
            anims = []
            if i < len(l_items):
                lt = Text(f"• {l_items[i]}", font_size=22, color=WHITE).move_to(LEFT * 2.6 + UP * y)
                anims.append(FadeIn(lt))
            if i < len(r_items):
                rt = Text(f"• {r_items[i]}", font_size=22, color=WHITE).move_to(RIGHT * 2.6 + UP * y)
                anims.append(FadeIn(rt))
            if anims:
                self.play(*anims, run_time=0.45)

        self.wait(max(duration - n * 0.45 - 1.5, 0.3))
