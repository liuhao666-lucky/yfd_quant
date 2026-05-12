import requests
import json

INDEX_CODE = "931160"  # 中证全指通信设备指数
URL = f"https://www.csindex.com.cn/csindex-home/perf/index-perf-oneday?indexCode={INDEX_CODE2}"

# 创建 Session，自动处理 Cookie
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.csindex.com.cn/",    # 从官网页面发起
})

# 第1步：先访问一次官网首页，获取基础 Cookie（可能不需要，但保稳）
print("正在连接中证指数官网...")
home_resp = session.get("https://www.csindex.com.cn/", timeout=10)
print(f"首页状态码: {home_resp.status_code}")

# 第2步：请求指数日表现接口
print(f"请求数据: {URL}")
resp = session.get(URL, timeout=10)
if resp.status_code == 200:
    data = resp.json()
    print("请求成功！返回数据：")
    print(json.dumps(data, indent=2, ensure_ascii=False))
else:
    print(f"请求失败，状态码: {resp.status_code}")
    print(resp.text[:300])