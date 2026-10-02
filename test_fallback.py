from manim import config as manim_config
manim_config.pixel_width  = 1080
manim_config.pixel_height = 1920
manim_config.frame_width  = 9
manim_config.frame_height = 16
from app.pipeline.manim_framework.base_scene import ChemistryScene
from manim import Text, UP
class GeneratedVideo(ChemistryScene):
    def construct(self):
        text = Text("Hello", font_size=36)
        self.play(text.animate.shift(UP))
