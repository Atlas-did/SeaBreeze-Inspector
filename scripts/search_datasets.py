"""风电叶片缺陷数据集搜索 & 下载工具"""
import urllib.request
import json
import sys

def search_modelscope(query: str) -> list:
    """搜索 ModelScope 数据集"""
    encoded = urllib.request.quote(query)
    url = f"https://modelscope.cn/api/v1/datasets?PageSize=15&PageNumber=1&Query={encoded}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        items = data.get("Data", {}).get("Items", [])
        results = []
        for item in items:
            results.append({
                "name": item.get("Name", "?"),
                "id": item.get("Id", ""),
                "desc": (item.get("Description") or "")[:120],
                "url": f"https://modelscope.cn/datasets/{item.get('Id', '')}"
            })
        return results
    except Exception as e:
        print(f"  ModelScope 搜索失败: {e}")
        return []

def search_opendatalab(query: str) -> list:
    """搜索 OpenDataLab 数据集"""
    encoded = urllib.request.quote(query)
    url = f"https://opendatalab.com/api/v1/datasets?keyword={encoded}&page_size=10"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        items = data.get("data", [])
        results = []
        for item in items:
            results.append({
                "name": item.get("name", "?"),
                "id": item.get("id", ""),
                "desc": (item.get("description") or "")[:120],
                "url": f"https://opendatalab.com/{item.get('id', '')}"
            })
        return results
    except Exception as e:
        print(f"  OpenDataLab 搜索失败: {e}")
        return []

if __name__ == "__main__":
    keywords = [
        "风机叶片缺陷",
        "风电叶片损伤",
        "wind turbine blade defect",
        "叶片表面缺陷",
        "风机叶片腐蚀",
        "crack detection blade",
        "turbine blade damage",
    ]
    
    all_results = {}
    for kw in keywords:
        print(f"\n{'='*50}")
        print(f"搜索: {kw}")
        print(f"{'='*50}")
        
        ms = search_modelscope(kw)
        if ms:
            print(f"  ModelScope ({len(ms)} 个):")
            for r in ms:
                print(f"    - {r['name']}")
                print(f"      {r['desc']}")
                print(f"      {r['url']}")
        
        od = search_opendatalab(kw)
        if od:
            print(f"  OpenDataLab ({len(od)} 个):")
            for r in od:
                print(f"    - {r['name']}")
                print(f"      {r['desc']}")
                print(f"      {r['url']}")
        
        if not ms and not od:
            print("  无结果")
    
    print("\n\n=== 完成 ===")
    print("如果以上平台都无结果，尝试手动:")
    print("  1. https://aistudio.baidu.com/datasetoverview (百度AI Studio)")
    print("  2. https://tianchi.aliyun.com/dataset (阿里天池)")
    print("  3. 搜索词: '风机叶片' 'wind turbine blade' 'blade defect'")
