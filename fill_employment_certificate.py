# -*- coding: utf-8 -*-
"""
将就业证明模板（图一）与公章（图二）、姓名手写图（图三）合成，并填写文字字段。
依赖：pip install pillow
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# 默认使用 Cursor 保存到工作区 assets 下的三张图（可按需改成你自己的路径）
DEFAULT_ASSETS = Path(r"C:\Users\User\.cursor\projects\d-biyesheji-Bilibilibs\assets")


def _find_asset(assets: Path, contains: str) -> Path:
    matches = sorted(assets.glob(f"*{contains}*"))
    if not matches:
        raise FileNotFoundError(f"在 {assets} 下未找到包含 {contains!r} 的文件")
    return matches[0]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for fp in (
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
    ):
        p = Path(fp)
        if p.is_file():
            return ImageFont.truetype(str(p), size=size)
    return ImageFont.load_default()


def _trim_name_rgba(im: Image.Image) -> Image.Image:
    """裁掉姓名图四周接近白底的边距，便于贴到横线上。"""
    rgba = im.convert("RGBA")
    g = rgba.split()[0]
    a = rgba.split()[3]
    w, h = rgba.size
    min_x, min_y, max_x, max_y = w, h, 0, 0
    for y in range(h):
        for x in range(w):
            if a.getpixel((x, y)) > 12 or g.getpixel((x, y)) < 245:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    if min_x > max_x:
        return im
    pad = 2
    x0 = max(min_x - pad, 0)
    y0 = max(min_y - pad, 0)
    x1 = min(max_x + pad, w - 1)
    y1 = min(max_y + pad, h - 1)
    return rgba.crop((x0, y0, x1 + 1, y1 + 1))


def compose(
    template: Path,
    seal: Path,
    name_png: Path,
    out: Path,
    *,
    major: str = "大数据工程",
    salary: str = "5000",
    date_text: str = "2026年4月30日",
) -> None:
    base = Image.open(template).convert("RGBA")
    W, H = base.size
    draw = ImageDraw.Draw(base)
    font_major = _load_font(15)
    font_salary = _load_font(19)
    font_date = _load_font(16)

    # 坐标按当前模板 610×623：专业横线较窄用较小字号；单位章在右下「单位盖章」区，勿压左侧学院章。
    draw.text((273, 145), major, fill=(0, 0, 0, 255), font=font_major, anchor="mm")
    draw.text((267, 256), salary, fill=(0, 0, 0, 255), font=font_salary, anchor="mm")
    draw.text((285, 488), date_text, fill=(0, 0, 0, 255), font=font_date, anchor="lm")

    name_img = Image.open(name_png).convert("RGBA")
    name_img = _trim_name_rgba(name_img)
    nh = 30
    nw = max(1, int(name_img.width * nh / name_img.height))
    name_img = name_img.resize((nw, nh), Image.Resampling.LANCZOS)
    nx = 118
    ny = 168
    base.alpha_composite(name_img, dest=(nx, ny))

    seal_img = Image.open(seal).convert("RGBA")
    target_w = min(98, W - 40)
    sh = max(1, int(target_w * seal_img.height / seal_img.width))
    seal_img = seal_img.resize((target_w, sh), Image.Resampling.LANCZOS)
    sx = 368
    sy = 362
    base.alpha_composite(seal_img, dest=(sx, sy))

    out.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").save(out, quality=95)
    print("Saved:", out.resolve())


def main() -> None:
    ap = argparse.ArgumentParser(description="合成就业证明填表图")
    ap.add_argument("--assets", type=Path, default=DEFAULT_ASSETS, help="资源目录")
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "employment_certificate_filled.png",
        help="输出 PNG 路径",
    )
    args = ap.parse_args()

    tpl = _find_asset(args.assets, "mmexport1778570009145")
    seal = _find_asset(args.assets, "ad45ac8d-ab5d-47e6-8cb6-f5f9b1d9660f")
    name_f = _find_asset(args.assets, "2911e28e-80ad-46a7-92ee-019987b05ee6")

    compose(tpl, seal, name_f, args.output)


if __name__ == "__main__":
    main()
