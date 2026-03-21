"""
각 분석 지도의 스크린샷 썸네일 생성
로컬 HTTP 서버 → Playwright Chromium → JPEG 저장
"""

import subprocess
import time
import os
import sys

BASE   = r'C:\Users\woosd\OneDrive\바탕 화면\작업\goyang-convenience-analysis'
PORT   = 8765
OUTDIR = os.path.join(BASE, 'images')
os.makedirs(OUTDIR, exist_ok=True)

MAPS = [
    ('goyang_voronoi_map.html',   'thumb_voronoi.jpg'),
    ('goyang_final_map.html',     'thumb_final.jpg'),
    ('goyang_satellite_map.html', 'thumb_satellite.jpg'),
    ('goyang_brand_map.html',     'thumb_brand.jpg'),
    ('goyang_demand_map.html',    'thumb_demand.jpg'),
    ('goyang_coverage_map.html',  'thumb_coverage.jpg'),
    ('goyang_brand_gap_map.html', 'thumb_brand_gap.jpg'),
    ('goyang_dong_density_map.html', 'thumb_dong_density.jpg'),
]

# 로컬 HTTP 서버 시작
print(f"HTTP 서버 시작 (포트 {PORT})...")
server = subprocess.Popen(
    [sys.executable, '-m', 'http.server', str(PORT), '--directory', BASE],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(1.5)

try:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1280, 'height': 720})

        for html_file, out_file in MAPS:
            url  = f'http://localhost:{PORT}/{html_file}'
            out  = os.path.join(OUTDIR, out_file)
            print(f"  스크린샷: {html_file} ...", end='', flush=True)
            try:
                page.goto(url, wait_until='networkidle', timeout=30000)
                time.sleep(3)   # 타일 로드 대기
                page.screenshot(path=out, type='jpeg', quality=85,
                                clip={'x':0,'y':0,'width':1280,'height':720})
                print(f" [OK] ({os.path.getsize(out)//1024}KB)")
            except Exception as e:
                print(f" [실패] {e}")

        browser.close()
        print("\n[OK] 썸네일 생성 완료")

except ImportError:
    print("playwright 미설치. 설치 후 재실행: pip install playwright && playwright install chromium")
finally:
    server.terminate()
    print("HTTP 서버 종료")
