"""数据集验证器 - 检查 YOLO 格式数据集完整性"""
import sys
from pathlib import Path

def verify_dataset(dataset_path: str) -> dict:
    """验证 YOLO 数据集，返回问题列表"""
    root = Path(dataset_path)
    issues = {"errors": [], "warnings": [], "stats": {}}
    
    if not root.exists():
        issues["errors"].append(f"路径不存在: {root}")
        return issues
    
    data_yaml = root / "data.yaml"
    if not data_yaml.exists():
        issues["errors"].append(f"找不到 data.yaml (可能格式选错，请重新下载选 YOLOv8)")
    else:
        issues["stats"]["data_yaml"] = "OK"
    
    images_no_label = 0
    empty_labels = 0
    format_errors = 0
    total_images = 0
    total_labels = 0
    
    for split in ["train", "valid", "test"]:
        split_path = root / split
        if not split_path.exists():
            continue
        
        img_dir = split_path / "images"
        lbl_dir = split_path / "labels"
        
        if not img_dir.exists():
            continue
        
        for img_file in img_dir.glob("*"):
            if img_file.suffix.lower() not in [".jpg", ".jpeg", ".png", ".bmp"]:
                continue
            total_images += 1
            label_file = lbl_dir / f"{img_file.stem}.txt"
            
            if not label_file.exists():
                images_no_label += 1
                continue
            
            total_labels += 1
            content = label_file.read_text().strip()
            
            if not content:
                empty_labels += 1
                continue
            
            for line_num, line in enumerate(content.split("\n"), 1):
                parts = line.strip().split()
                if len(parts) != 5:
                    format_errors += 1
                    issues["errors"].append(
                        f"{label_file}:{line_num} 格式异常 (需要5个数字: class x_center y_center w h)"
                    )
                    continue
                try:
                    vals = [float(x) for x in parts]
                    if any(v < 0 or v > 1 for v in vals[1:]):
                        format_errors += 1
                        issues["errors"].append(
                            f"{label_file}:{line_num} 坐标超出 0~1 范围: {vals[1:]}"
                        )
                except ValueError:
                    format_errors += 1
                    issues["errors"].append(f"{label_file}:{line_num} 非数字: {line}")
    
    issues["stats"]["total_images"] = total_images
    issues["stats"]["total_labels"] = total_labels
    issues["stats"]["images_without_labels"] = images_no_label
    issues["stats"]["empty_labels"] = empty_labels
    issues["stats"]["format_errors"] = format_errors
    
    if images_no_label > 0:
        issues["warnings"].append(f"{images_no_label} 张图片无对应标注 (可能是负样本，正常)")
    if empty_labels > 0:
        issues["warnings"].append(f"{empty_labels} 个空标注文件 (表示该图无缺陷，正常)")
    
    return issues

if __name__ == "__main__":
    path = input("输入数据集路径 (如 data/raw/wind-turbine-damage): ").strip()
    if not path:
        print("未输入路径")
        sys.exit(1)
    
    result = verify_dataset(path)
    
    print("\n" + "="*50)
    print("数据集验证报告")
    print("="*50)
    
    stats = result["stats"]
    print(f"  总图片数: {stats.get('total_images', 0)}")
    print(f"  总标注数: {stats.get('total_labels', 0)}")
    print(f"  data.yaml: {stats.get('data_yaml', '未找到')}")
    
    if result["errors"]:
        print(f"\n❌ 致命错误 ({len(result['errors'])}):")
        for e in result["errors"][:20]:
            print(f"  - {e}")
    
    if result["warnings"]:
        print(f"\n⚠️ 警告 ({len(result['warnings'])}):")
        for w in result["warnings"]:
            print(f"  - {w}")
    
    if not result["errors"]:
        print("\n✅ 数据集格式验证通过！")
