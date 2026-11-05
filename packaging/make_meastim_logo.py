"""Make the MEA-Stim logo from the MEA-NAP logo's own artwork.

The neurons and the letters M, E and A are lifted from ``mea-nap-logo.png``; the
rest (bolt, sparks, network S, T, I) is drawn here. Coordinates are that logo's
pixels. Not part of the build: run it by hand after changing something here, and
commit the PNG it writes.
"""

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parents[1] / "src" / "meanap" / "gui" / "assets"
SOURCE = ASSETS / "mea-nap-logo.png"
OUT = ASSETS / "meastim-logo.png"

BLUE = (23, 135, 214, 255)
GREEN = (126, 160, 14, 255)
YELLOW = (253, 181, 1, 255)
GREY = (166, 166, 166, 255)

WIDTH, HEIGHT = 1038, 675
SUPERSAMPLE = 4

#: Horizontal extent of the wordmark, which the neurons are centred over.
WORDMARK_X = (34, 1003)
#: Left edge, right edge and destination x of each letter reused from the source.
LETTERS = [(30, 180, 30), (214, 292, 214), (313, 444, 313), (30, 180, 860)]
HYPHEN = (467, 543, 530, 560)
#: Same stroke (20) and cap height (466-593) as the source's letters.
T_BAR = (706, 466, 798, 485)
T_STEM = (742, 466, 762, 593)
I_STEM = (822, 466, 842, 593)

#: The S: top right, top left, middle left, middle right, bottom right, bottom left.
S = [(667, 463), (550, 463), (537, 527), (654, 527), (641, 590), (524, 590)]
#: The yellow network behind it, and which of its nodes join which, or join the S.
NODES = {"a": (496, 432), "b": (583, 436), "c": (481, 476), "d": (606, 495),
         "f": (512, 549), "g": (686, 552), "h": (596, 558), "i": (486, 618),
         "j": (641, 636), "k": (574, 636)}
EDGES = ["ab", "ac", "cf", "fi", "bd", "ik", "hk", "hj", "dg"]
EDGES_TO_S = [("b", 0), ("c", 1), ("d", 0), ("d", 2), ("g", 0), ("h", 3),
              ("h", 5), ("f", 2), ("i", 5), ("k", 5), ("j", 4)]

#: The bolt's outline in a unit box, with the tip that strikes the neuron at index 3.
BOLT = [(.58, 0), (.08, .56), (.44, .56), (.28, 1), (.92, .36), (.54, .36), (.84, 0)]
BOLT_TIP, BOLT_ANGLE, BOLT_SIZE = (892, 126), -68, (92, 178)
SPARKS = [(968, 92, 992, 76), (983, 128, 1012, 124),
          (957, 206, 972, 228), (872, 205, 858, 226)]

#: Bridges the middle neuron's process where the removed dark neuron's hand covered it.
BRIDGE = [(1236, 347), (1255, 347), (1274, 339), (1280, 351), (1262, 356), (1238, 361)]


class Layer:
    """A transparent layer drawn supersampled, so its edges come out antialiased."""

    def __init__(self, width: int = WIDTH) -> None:
        self.size = (width, HEIGHT)
        self.im = Image.new("RGBA", (width * SUPERSAMPLE, HEIGHT * SUPERSAMPLE), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.im)

    @staticmethod
    def _scaled(points):
        return [(x * SUPERSAMPLE, y * SUPERSAMPLE) for x, y in points]

    def line(self, a, b, width, colour):
        self.draw.line(self._scaled([a, b]), fill=colour, width=int(width * SUPERSAMPLE))

    def dot(self, centre, radius, colour):
        x, y = self._scaled([centre])[0]
        r = radius * SUPERSAMPLE
        self.draw.ellipse((x - r, y - r, x + r, y + r), fill=colour)

    def polygon(self, points, colour):
        self.draw.polygon(self._scaled(points), fill=colour)

    def rect(self, box, colour):
        x0, y0, x1, y1 = box
        self.draw.rectangle((*self._scaled([(x0, y0)])[0], *self._scaled([(x1, y1)])[0]),
                            fill=colour)

    def image(self) -> Image.Image:
        return self.im.resize(self.size, Image.BOX)


def split_source():
    """The source logo as three-neuron artwork, and a function that cuts out a letter."""
    src = np.asarray(Image.open(SOURCE).convert("RGBA")).astype(int)
    r, g, b, alpha = (src[..., i] for i in range(4))
    yy, xx = np.mgrid[:src.shape[0], :src.shape[1]]

    def masked(mask):
        out = src.copy()
        out[~mask, 3] = 0
        return Image.fromarray(out.astype("uint8"))

    network = (r - b > 60) | (g - b > 60)
    blue = b - r > 60
    light_grey = (abs(r - g) < 6) & (abs(g - b) < 6) & (r >= 155)
    faces = (r < 40) & (g < 40) & (b < 40) & (yy < 300) & (xx < 1200)
    neurons = masked((light_grey | faces | (blue & (yy <= 440)))
                     & (alpha > 0) & ~network & (yy < 445))

    letters = blue & (yy > 440) & (xx < 930)

    def letter(x0, x1):
        return masked(letters & (xx >= x0) & (xx < x1)).crop((x0, 440, x1, 620))

    return neurons, letter


def bolt_outline(tip):
    w, h = BOLT_SIZE
    tip_u, tip_v = BOLT[3]
    a = math.radians(BOLT_ANGLE)
    points = []
    for u, v in BOLT:
        x, y = (u - tip_u) * w, (v - tip_v) * h
        points.append((tip[0] + x * math.cos(a) - y * math.sin(a),
                       tip[1] + x * math.sin(a) + y * math.cos(a)))
    return points


def wordmark_art() -> Image.Image:
    art = Layer()
    art.rect(HYPHEN, BLUE)
    for a, b in EDGES:
        art.line(NODES[a], NODES[b], 4.5, YELLOW)
    for node, s_index in EDGES_TO_S:
        art.line(NODES[node], S[s_index], 4.5, YELLOW)
    for centre in NODES.values():
        art.dot(centre, 10.5, YELLOW)
    for a, b in zip(S, S[1:]):
        art.line(a, b, 15, GREEN)
    for centre in S:
        art.dot(centre, 16.5, GREEN)
    for box in (T_BAR, T_STEM, I_STEM):
        art.rect(box, BLUE)
    return art.image()


def make_logo() -> Image.Image:
    neurons, letter = split_source()

    bridge = Layer(neurons.width)
    bridge.polygon(BRIDGE, GREY)
    neurons.alpha_composite(bridge.image())

    x0, _, x1, _ = neurons.getbbox()
    shift = (x0 + x1) // 2 - sum(WORDMARK_X) // 2

    logo = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    logo.alpha_composite(wordmark_art())
    for x0, x1, x in LETTERS:
        logo.alpha_composite(letter(x0, x1), (x, 440))

    # The bolt goes behind the neurons, so it stops at the cell body's edge.
    strike = Layer()
    strike.polygon(bolt_outline((BOLT_TIP[0] - shift, BOLT_TIP[1])), YELLOW)
    for xa, ya, xb, yb in SPARKS:
        strike.line((xa - shift, ya), (xb - shift, yb), 8, YELLOW)
    logo.alpha_composite(strike.image())

    logo.alpha_composite(neurons.crop((shift, 0, shift + WIDTH, HEIGHT)))
    return logo


if __name__ == "__main__":
    make_logo().save(OUT)
    print(f"logo -> {OUT}")
