"""LabelMe JSON 转 YOLO txt 格式"""
import json
from pathlib import Path

LABEL_MAP = {
    "crack": 0,
    "corrosion": 1,
    "leading_edge_damage": 2,
    "erosion": 2,  # erosion 映射到 leading_edge_damage
}

def convert_labelme_to_yolo(json_path: str, output_dir: str):
    """单个 LabelMe JSON 转 YOLO txt"""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    img_w = data.get("imageWidth", 0)
    img_h = data.get("imageHeight", 0)
    
    if img_w == 0 or img_h == 0:
        print(f"  [SKIP] {json_path}: 缺少图片尺寸")
        return
    
    shapes = data.get("shapes", [])
    yolo_lines = []
    
    for shape in shapes:
        label = shape.get("label", "").strip().lower().replace(" ", "_")
        if label not in LABEL_MAP:
            print(f"  [WARN] 未知类别 '{label}', 跳过")
            continue
        
        cls_id = LABEL_MAP[label]
        points = shape["points"]
        
        if shape["shape_type"] == "rectangle":
            x1, y1 = points[0]
            x2, y2 = points[1]
            x_center = ((x1 + x2) / 2) / img_w
            y_center = ((y1 + y2) / 2) / img_h
            w = abs(x2 - x1) / img_w
            h = abs(y2 - y1) / img_h
        elif shape["shape_type"] == "polygon":
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)
            x_center = ((x1 + x2) / 2) / img_w
            y_center = ((y1 + y2) / 2) / img_h
            w = (x2 - x1) / img_w
            h = (y2 - y1) / img_h
        else:
            continue
        
        x_center = max(0, min(1, x_center))
        y_center = max(0, min(1, y_center))
        w = max(0, min(1, w))
        h = max(0, min(1, h))
        
        yolo_lines.append(f"{cls_id} {x_center:.6f} {y_center:.6f} {w:.6f} {h:.6f}")
    
    out_path = Path(output_dir) / f"{Path(json_path).stem}.txt"
    out_path.write_text("\n".join(yolo_lines), encoding="utf-8")
    print(f"  [OK] {Path(json_path).name} -> {len(yolo_lines)} 个标注")

def convert_directory(input_dir: str, output_dir: str):
    """批量转换目录下所有 LabelMe JSON"""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    json_files = list(input_path.glob("*.json"))
    print(f"找到 {len(json_files)} 个 JSON 文件")
    
    for jf in json_files:
        convert_labelme_to_yolo(str(jf), str(output_path))
    
    print(f"\n完成! 输出: {output_path}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("用法: python labelme2yolo.py <LabelMe JSON目录> <YOLO输出目录>")
        sys.exit(1)
    convert_directory(sys.argv[1], sys.argv[2])
