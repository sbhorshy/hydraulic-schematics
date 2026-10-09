#!/usr/bin/env python3
"""只读核对:系统原理图各设备实例的比例(缩放因子 k)是否正确。

判定基准(symbol-campaign 定案):画布即图上单位——layout 声明 w/h 应等于
符号文件 viewBox(经 rot 交换前的原生画布),即 k_x = k_y = 1;
渲染 SVG 实例组放置 scale 亦应为 1。非均匀(k_x != k_y)即比例失真。

用法: python check_proportions.py   (工作目录内运行)
退出码 0 全部通过 / 1 存在超差。
"""
import json
import re
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
TOL = 0.005  # 0.5% 容差(圆整值如 67.6056→67.61、272.016→272.01)


def read_viewbox(svg_path: Path):
    """返回 (vb_w, vb_h, svg_w_attr, svg_h_attr)。"""
    root = ET.parse(svg_path).getroot()
    vb = root.get("viewBox")
    if not vb:
        return None
    x, y, w, h = (float(v) for v in vb.replace(",", " ").split())
    return (w, h, root.get("width"), root.get("height"))


def parse_inst_transforms(svg_path: Path):
    """从成品 SVG 抽取每个 inst-<NODE> 组的放置 scale。"""
    text = svg_path.read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(
        r'<g id="inst-([^"]+)" transform="translate\(([-\d.]+),([-\d.]+)\)'
        r'[^"]*?rotate\((\d+)\) scale\(([\d.]+)\)', text
    ):
        out[m.group(1)] = {
            "x": float(m.group(2)), "y": float(m.group(3)),
            "rot": int(m.group(4)), "scale": float(m.group(5)),
        }
    return out


def main():
    layout = json.loads((HERE / "1#系统.layout.json").read_text(encoding="utf-8"))
    skill_cat_path = Path(__file__).resolve().parents[1] / (
        ".agents/skills/hydraulic-schematic/assets/component-library/"
        "component-catalog.json")
    skill_cat = {}
    try:
        raw = json.loads(skill_cat_path.read_text(encoding="utf-8"))
        for c in raw.get("components", []):
            sym = c.get("symbol", {}).get("asset")
            fp = c.get("footprint") or c.get("symbol", {}).get("footprint")
            if sym and fp:
                skill_cat[sym] = fp
    except Exception as e:
        print(f"[warn] skill catalog 读取失败: {e}")

    renders = parse_inst_transforms(HERE / "1#系统原理图.svg")

    rows, fails = [], []
    for name, node in layout["nodes"].items():
        sym_rel = node["symbol"]
        sym_path = HERE / sym_rel
        vb = read_viewbox(sym_path) if sym_path.exists() else None
        w, h, rot = node.get("w"), node.get("h"), node.get("rot", 0)
        if vb is None:
            fails.append(f"{name}: 符号缺失或无 viewBox ({sym_rel})")
            rows.append((name, sym_rel, w, h, rot, None, None, None, None))
            continue
        vb_w, vb_h = vb[0], vb[1]
        kx, ky = w / vb_w, h / vb_h
        verdict = "PASS" if abs(kx - 1) <= TOL and abs(ky - 1) <= TOL else "FAIL"
        if abs(kx - ky) > TOL:
            verdict = "FAIL(非均匀)"
        if verdict != "PASS":
            fails.append(
                f"{name}: k=({kx:.4f},{ky:.4f}) viewBox=({vb_w:g}x{vb_h:g}) "
                f"声明=({w:g}x{h:g})")
        r = renders.get(name)
        scale_ok = r is None or abs(r["scale"] - 1) <= TOL
        if not scale_ok:
            fails.append(f"{name}: 渲染放置 scale={r['scale']} != 1")
        # catalog footprint 交叉对账(仅参考,符号本地覆盖优先)
        cat_fp = skill_cat.get(Path(sym_rel).name)
        rows.append((name, Path(sym_rel).name, w, h, rot,
                     f"{vb_w:g}x{vb_h:g}", f"{kx:.4f}/{ky:.4f}",
                     cat_fp, ("scale=1" if scale_ok else "scale!=1")))

    print(f"{'实例':<10}{'符号文件':<44}{'声明w×h':<16}{'rot':<5}"
          f"{'viewBox':<16}{'k_x/k_y':<14}{'catalog占位':<16}{'渲染'}")
    for r in rows:
        print(f"{r[0]:<10}{str(r[1]):<44}{f'{r[2]:g}×{r[3]:g}':<16}{str(r[4]):<5}"
              f"{str(r[5]):<16}{str(r[6]):<14}{str(r[7]):<16}{r[8]}")

    print(f"\n共 {len(rows)} 实例;容差 ±{TOL:.1%}")
    if fails:
        print("\n[FAIL] 超差项:")
        for f_ in fails:
            print("  -", f_)
        sys.exit(1)
    print("\n[PASS] 全部实例 k=1(画布即图上单位),渲染放置无缩放,无非均匀失真。")
    sys.exit(0)


if __name__ == "__main__":
    main()
