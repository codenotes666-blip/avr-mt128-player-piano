from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "static" / "images" / "avr-mt128-rear.jpg"
OUTPUT = ROOT / "static" / "images" / "projects" / "piano-hall-sensor"
FONT_PATH = Path("C:/Windows/Fonts/segoeuib.ttf")
FONT = ImageFont.truetype(str(FONT_PATH), 16)
SMALL_FONT = ImageFont.truetype(str(FONT_PATH), 12)

TEAL = "#007f73"
ORANGE = "#e85f2b"
BLUE = "#126da3"
WHITE = "#ffffff"
BLACK = "#111a17"


def label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, color: str) -> None:
    left, top, right, bottom = draw.textbbox(xy, text, font=FONT, anchor="mm")
    draw.rounded_rectangle((left - 7, top - 4, right + 7, bottom + 4), 4, fill=WHITE, outline=color, width=3)
    draw.text(xy, text, font=FONT, fill=BLACK, anchor="mm")


def marker(draw: ImageDraw.ImageDraw, pin: tuple[int, int], text_xy: tuple[int, int], text: str, color: str) -> None:
    draw.line((pin, text_xy), fill=color, width=4)
    draw.ellipse((pin[0] - 8, pin[1] - 8, pin[0] + 8, pin[1] + 8), fill=color, outline=WHITE, width=2)
    label(draw, text_xy, text, color)


def save_overview(source: Image.Image) -> None:
    scale = 2
    image = source.resize((source.width * scale, source.height * scale), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(image)
    boxes = {
        "ADC": ((215, 160, 280, 198), TEAL),
        "EXT1": ((285, 160, 390, 198), ORANGE),
        "EXT2": ((398, 160, 505, 198), BLUE),
    }
    for name, (box, color) in boxes.items():
        scaled = tuple(value * scale for value in box)
        draw.rounded_rectangle(scaled, 6, outline=color, width=6)
        label(draw, ((box[0] + box[2]) * scale // 2, (box[1] - 12) * scale), name, color)
    image.save(OUTPUT / "mt128-connector-overview.webp", "WEBP", quality=94, method=6)


def make_closeup(
    source: Image.Image,
    crop: tuple[int, int, int, int],
    pins: list[tuple[tuple[int, int], str, str]],
    filename: str,
) -> None:
    left, top, right, bottom = crop
    crop_image = source.crop(crop).resize(((right - left) * 4, (bottom - top) * 4), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (crop_image.width, crop_image.height + 90), WHITE)
    canvas.paste(crop_image, (0, 90))
    draw = ImageDraw.Draw(canvas)
    for index, (pin, text, color) in enumerate(pins):
        local_pin = ((pin[0] - left) * 4, (pin[1] - top) * 4 + 90)
        if len(pins) > 1:
            text_x = int(canvas.width * (index + 1) / (len(pins) + 1))
        else:
            text_x = max(80, min(canvas.width - 80, local_pin[0]))
        marker(draw, local_pin, (text_x, 34), text, color)
    draw.text((12, 76), "Component side shown · LCD is on the opposite side", font=SMALL_FONT, fill="#40534b")
    canvas.save(OUTPUT / filename, "WEBP", quality=95, method=6)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    source = Image.open(SOURCE).convert("RGB")
    save_overview(source)
    make_closeup(
        source,
        (205, 145, 285, 210),
        [((243, 171), "ADC pin 3 · ADC0/PF0", TEAL)],
        "adc-pin-3.webp",
    )
    make_closeup(
        source,
        (385, 145, 515, 210),
        [
            ((477, 170), "EXT2 pin 1 · GND", TEAL),
            ((477, 181), "EXT2 pin 2 · +5 V", ORANGE),
        ],
        "ext2-pins-1-2.webp",
    )
    make_closeup(
        source,
        (275, 145, 395, 210),
        [((310, 182), "EXT1 pin 12 · PD5", BLUE)],
        "ext1-pin-12.webp",
    )
    print(f"Generated project connector images in {OUTPUT}")


if __name__ == "__main__":
    main()