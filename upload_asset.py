"""上传 Release 附件（uploads.github.com 走本地代理兜底）。"""
import os
import sys
import requests

OWNER = os.environ.get("GH_OWNER", "Seiran-Tsurumi")
REPO = os.environ.get("GH_REPO", "BiliDownloader")
TAG = os.environ.get("GH_TAG", "v2.0.0")
PROXY = os.environ.get("GH_PROXY", "http://127.0.0.1:12348")
API = "https://api.github.com"
UPLOAD = "https://uploads.github.com"
ASSET = "dist/BiliDownloader.exe"

token = os.environ.get("GH_TOKEN", "").strip()
if not token:
    sys.exit("GH_TOKEN 未设置")
session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "BiliDownloader-publish",
})
rel = session.get(f"{API}/repos/{OWNER}/{REPO}/releases/tags/{TAG}", timeout=30)
if rel.status_code != 200:
    sys.exit(f"读取 Release 失败：{rel.status_code} {rel.text[:200]}")
release = rel.json()
print("Release:", release["html_url"], "id=", release["id"])
for asset in release.get("assets", []):
    if asset["name"] == "BiliDownloader.exe":
        d = session.delete(f"{API}/repos/{OWNER}/{REPO}/releases/assets/{asset['id']}", timeout=60)
        print("删除旧附件:", d.status_code)
data = open(ASSET, "rb").read()
print("上传字节:", len(data))
proxies = {"http": PROXY, "https": PROXY}
r = session.post(
    f"{UPLOAD}/repos/{OWNER}/{REPO}/releases/{release['id']}/assets?name=BiliDownloader.exe",
    headers={"Content-Type": "application/octet-stream"},
    data=data, proxies=proxies, timeout=(30, 1800),
)
print("上传响应:", r.status_code)
if r.status_code >= 300:
    print(r.text[:500])
    sys.exit(1)
info = r.json()
print("下载地址:", info.get("browser_download_url"))
print("大小:", info.get("size"))
