"""Download NotoSansTC font for Chinese PDF rendering. Run once before first use."""
import os
import urllib.request

FONT_URL = (
    "https://github.com/googlefonts/noto-cjk/raw/main/Sans/Variable/TTF/Subset/"
    "NotoSansTC-VF.ttf"
)
FONT_PATH = os.path.join(os.path.dirname(__file__), "..", "bot", "fonts", "NotoSansTC-Regular.ttf")

def download_font():
    font_path = os.path.abspath(FONT_PATH)
    if os.path.exists(font_path):
        print(f"Font already exists: {font_path}")
        return
    os.makedirs(os.path.dirname(font_path), exist_ok=True)
    print("Downloading NotoSansTC font (~11MB)...")
    urllib.request.urlretrieve(FONT_URL, font_path)
    print(f"Font saved to: {font_path}")

if __name__ == "__main__":
    download_font()
