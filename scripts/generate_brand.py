"""Generate Home Assistant brand images for Chirp.

The artwork is original: a small yellow bird perched on a branch, chirping, on a dark
rounded square. It is drawn from primitives at 4x scale and downsampled, so no
source image, external font file or network access is needed. Run with
Pillow 12.3.0 for reproducible PNGs.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BRAND = Path(__file__).resolve().parents[1] / "custom_components/chirp/brand"
SIZE = 512
SCALE = 4
NAVY = "#1b2a41"
YELLOW = "#ffd23f"
GOLD = "#f2a900"
ORANGE = "#ff8c1a"
BRANCH = "#8a6d3b"
WORDMARK = "#e0a100"


def draw_icon() -> Image.Image:
    """Draw the 512px RGBA app icon."""
    s = SCALE
    image = Image.new("RGBA", (SIZE * s, SIZE * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)

    def box(x0, y0, x1, y1):
        return [x0 * s, y0 * s, x1 * s, y1 * s]

    def poly(points):
        return [(x * s, y * s) for x, y in points]

    d.rounded_rectangle(box(0, 0, SIZE - 1, SIZE - 1), radius=104 * s, fill=NAVY)
    # Branch and legs.
    d.line(poly([(150, 446), (350, 446)]), fill=BRANCH, width=16 * s)
    for x in (232, 288):
        d.line(poly([(x, 392), (x, 442)]), fill=ORANGE, width=9 * s)
    # Tail, body, wing, head.
    d.polygon(poly([(160, 300), (62, 372), (82, 396), (190, 352)]), fill=GOLD)
    d.ellipse(box(124, 224, 388, 410), fill=YELLOW)
    d.ellipse(box(252, 134, 408, 290), fill=YELLOW)
    d.polygon(poly([(300, 148), (322, 112), (342, 152)]), fill=YELLOW)
    d.ellipse(box(168, 276, 306, 378), fill=GOLD)
    # Beak and eye.
    d.polygon(poly([(398, 196), (456, 218), (398, 242)]), fill=ORANGE)
    d.ellipse(box(338, 188, 362, 212), fill=NAVY)
    d.ellipse(box(347, 193, 355, 201), fill="#ffffff")
    # Chirp: two sound arcs in front of the beak.
    for radius in (34, 60):
        centre = (446, 150)
        d.arc(
            box(
                centre[0] - radius,
                centre[1] - radius,
                centre[0] + radius,
                centre[1] + radius,
            ),
            start=-70,
            end=10,
            fill=YELLOW,
            width=10 * s,
        )
    return image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def main() -> None:
    """Write icon.png, icon@2x.png, logo.png and logo@2x.png."""
    BRAND.mkdir(parents=True, exist_ok=True)
    icon = draw_icon()
    icon.save(BRAND / "icon@2x.png", optimize=True)
    icon.resize((256, 256), Image.Resampling.LANCZOS).save(
        BRAND / "icon.png", optimize=True
    )

    # Pillow bundles Aileron Regular, so regeneration needs no system fonts.
    font = ImageFont.load_default(size=448)
    bounds = font.getbbox("Chirp")
    wordmark = Image.new("RGBA", (bounds[2] - bounds[0], bounds[3] - bounds[1]))
    ImageDraw.Draw(wordmark).text(
        (-bounds[0], -bounds[1]), "Chirp", font=font, fill=WORDMARK
    )
    gap = 96
    logo = Image.new("RGBA", (SIZE + gap + wordmark.width, SIZE))
    logo.alpha_composite(icon, (0, 0))
    logo.alpha_composite(wordmark, (SIZE + gap, (SIZE - wordmark.height) // 2))
    logo = logo.crop(logo.getbbox())
    logo.save(BRAND / "logo@2x.png", optimize=True)
    logo.resize((logo.width // 2, logo.height // 2), Image.Resampling.LANCZOS).save(
        BRAND / "logo.png", optimize=True
    )


if __name__ == "__main__":
    main()
