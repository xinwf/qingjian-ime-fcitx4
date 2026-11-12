#!/usr/bin/env python3
"""生成青简的 Fcitx4 classic-ui 皮肤：fcitx_skin.conf 与背景/图标图片。

Fcitx4 的候选窗由 classic-ui 绘制，皮肤从 /usr/share/fcitx/skin/<id>/fcitx_skin.conf 读。
青简自绘渲染器的那套 theme.json 用不进来，但配色、字号、边距能映射到这个格式里。
改了颜色或尺寸后重跑：python3 apps/linux/fcitx4/skin/generate.py

五套皮肤：简白（白底黑字）、深黑（黑底白字）、青简绿、青简橙、青简蓝。
前两套与青简渲染器的浅色/深色一致；后三套把 accent 铺成背景，绿/橙/蓝能一眼分辨。
"""
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
ICON = ROOT / "assets/icon/fcitx4.png"

# 简白 / 深黑：与 crates/qingjian-render/themes/qingjian/theme.json 的 surface、text 对齐
LIGHT = {
    "surface": (255, 255, 255),
    "text": (40, 40, 40),
    "gloss": (90, 90, 90),
    "faint": (130, 130, 130),
    "fresh": (255, 141, 40),
    "cloud": (0, 195, 208),
    "accent": (148, 190, 82),
}
DARK = {
    "surface": (30, 30, 30),
    "text": (235, 235, 235),
    "gloss": (200, 200, 200),
    "faint": (140, 140, 140),
    "fresh": (255, 146, 48),
    "cloud": (0, 210, 224),
    "accent": (51, 111, 51),
}
# 青简绿：原主题的 accent #94be52 铺成淡绿底，文字转深绿
GREEN = {
    "surface": (238, 245, 226),
    "text": (34, 51, 15),
    "gloss": (74, 97, 43),
    "faint": (122, 143, 96),
    "fresh": (224, 106, 10),
    "cloud": (0, 145, 130),
    "accent": (123, 168, 62),
}
# 青简橙：暖橙底，首候选加深成橙红
ORANGE = {
    "surface": (255, 244, 232),
    "text": (74, 43, 16),
    "gloss": (122, 82, 43),
    "faint": (168, 128, 90),
    "fresh": (240, 96, 16),
    "cloud": (0, 145, 150),
    "accent": (226, 122, 44),
}
# 青简蓝：晴蓝底，首候选与强调都用蓝
BLUE = {
    "surface": (238, 245, 255),
    "text": (22, 50, 79),
    "gloss": (58, 88, 120),
    "faint": (120, 150, 180),
    "fresh": (22, 119, 255),
    "cloud": (0, 150, 190),
    "accent": (47, 111, 237),
}

SKINS = (
    ("qingjian-light", "简白", "白底黑字（与青简浅色一致）", LIGHT),
    ("qingjian-dark", "深黑", "黑底白字（与青简深色一致）", DARK),
    ("qingjian", "青简绿", "青简绿：淡绿底、深绿字", GREEN),
    ("qingjian-orange", "青简橙", "暖橙底、深棕字", ORANGE),
    ("qingjian-blue", "青简蓝", "晴蓝底、深蓝字", BLUE),
)

SKIN_CONF = """[SkinInfo]
Name={name}
Version=1
Author=青简
Desc={desc}

[SkinFont]
FontSize={font_size}
MenuFontSize=13
RespectDPI=True
TipColor={gloss}
InputColor={text}
IndexColor={faint}
FirstCandColor={fresh}
UserPhraseColor={cloud}
CodeColor={text}
OtherColor={text}
ActiveMenuColor={on_accent}
InactiveMenuColor={gloss}

[SkinMainBar]
BackImg=bar.png
Logo=logo.png
Eng=en.png
Active=cn.png
MarginLeft=4
MarginRight=4
MarginTop=4
MarginBottom=4
UseCustomTextIconColor=True
ActiveTextIconColor={accent}
InactiveTextIconColor={faint}

[SkinInputBar]
BackImg=input.png
MarginLeft=12
MarginRight=12
MarginTop=8
MarginBottom=8
CursorColor={fresh}
InputPos=0
OutputPos=0
BackArrow=prev.png
ForwardArrow=next.png
BackArrowX=10
BackArrowY=12
ForwardArrowX=6
ForwardArrowY=12

[SkinTrayIcon]
Active=active.png
Inactive=inactive.png

[SkinMenu]
BackImg=menu.png
MarginLeft=8
MarginRight=8
MarginTop=6
MarginBottom=6
ActiveColor={accent}
LineColor={faint}

[SkinKeyboard]
KeyColor={accent}
"""


def rgb(color):
    return " ".join(str(c) for c in color)


def luminance(color):
    r, g, b = (c / 255 for c in color[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def border_for(palette):
    # 浅底用淡黑边，深底用淡白边
    return (0, 0, 0, 26) if luminance(palette["surface"]) > 0.5 else (255, 255, 255, 34)


def rounded(size, fill, radius, border=None):
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=fill, outline=border, width=1
    )
    return image


def tray_icon(size, color=None, alpha=255):
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    if not ICON.is_file():
        return image
    icon = Image.open(ICON).convert("RGBA").resize(size, Image.LANCZOS)
    if color is not None:
        # 未激活时压成单色，与 Fcitx4 其他托盘图标的习惯一致
        gray = icon.convert("L").convert("RGBA")
        gray.putalpha(icon.getchannel("A").point(lambda a: a * alpha // 255))
        return gray
    return icon


def text_icon(size, text, color, font_size=None):
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    fonts = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    font = None
    for path in fonts:
        if Path(path).is_file():
            try:
                font = ImageFont.truetype(path, font_size or int(size[1] * 0.78))
                break
            except OSError:
                continue
    if font is None:
        font = ImageFont.load_default()
    box = draw.textbbox((0, 0), text, font=font)
    draw.text(
        ((size[0] - (box[2] - box[0])) / 2 - box[0], (size[1] - (box[3] - box[1])) / 2 - box[1]),
        text,
        font=font,
        fill=color,
    )
    return image


def arrow(size, direction, color):
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    w, h = size
    if direction == "left":
        points = [(w - 1, 0), (0, h // 2), (w - 1, h - 1)]
    else:
        points = [(0, 0), (w - 1, h // 2), (0, h - 1)]
    draw.polygon(points, fill=color)
    return image


def build(skin_id, name, desc, palette, font_size=16):
    out = HERE / skin_id
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    border = border_for(palette)
    surface = palette["surface"] + (255,)
    rounded((200, 100), surface, 12, border).save(out / "input.png")
    rounded((200, 40), surface, 10, border).save(out / "bar.png")
    rounded((200, 40), surface, 10, border).save(out / "menu.png")
    tray_icon((22, 22)).save(out / "active.png")
    tray_icon((22, 22), palette["faint"], 150).save(out / "inactive.png")
    tray_icon((22, 22)).save(out / "logo.png")
    text_icon((24, 24), "中", palette["text"]).save(out / "cn.png")
    text_icon((24, 24), "EN", palette["faint"], 11).save(out / "en.png")
    arrow((6, 12), "left", palette["faint"]).save(out / "prev.png")
    arrow((6, 12), "right", palette["faint"]).save(out / "next.png")

    values = {key: rgb(value) for key, value in palette.items()}
    # 菜单高亮：深色底用白字，浅色底用深字
    values["on_accent"] = "255 255 255" if luminance(palette["accent"]) < 0.6 else "40 40 40"
    values.update(name=name, desc=desc, font_size=font_size)
    (out / "fcitx_skin.conf").write_text(SKIN_CONF.format(**values), encoding="utf-8")


def main():
    for skin_id, name, desc, palette in SKINS:
        build(skin_id, name, desc, palette)
        print(skin_id, name, "->", len(list((HERE / skin_id).iterdir())), "个文件")


if __name__ == "__main__":
    main()
