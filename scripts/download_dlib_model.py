"""下载dlib人脸关键点模型文件"""

import os
import urllib.request
from pathlib import Path

# 模型文件URL（dlib官方）
MODEL_URL = "http://dlib.net/files/shape_predictor_68_face_landmarks.dat.bz2"

# 本地保存路径
MODEL_DIR = Path.home() / ".dlib" / "models"
MODEL_FILE = MODEL_DIR / "shape_predictor_68_face_landmarks.dat"
COMPRESSED_FILE = MODEL_DIR / "shape_predictor_68_face_landmarks.dat.bz2"

def download_model():
    """下载并解压模型文件"""
    # 创建目录
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    if MODEL_FILE.exists():
        print(f"✅ 模型文件已存在: {MODEL_FILE}")
        return str(MODEL_FILE)

    print(f"⏳ 开始下载模型文件...")
    print(f"   URL: {MODEL_URL}")
    print(f"   保存到: {COMPRESSED_FILE}")

    try:
        # 下载压缩文件
        urllib.request.urlretrieve(MODEL_URL, COMPRESSED_FILE)
        print(f"✅ 下载完成: {COMPRESSED_FILE}")

        # 解压文件
        import bz2
        with bz2.open(COMPRESSED_FILE, 'rb') as f_in:
            with open(MODEL_FILE, 'wb') as f_out:
                f_out.write(f_in.read())

        print(f"✅ 解压完成: {MODEL_FILE}")
        print(f"   文件大小: {os.path.getsize(MODEL_FILE) / 1024 / 1024:.1f} MB")

        # 删除压缩文件
        COMPRESSED_FILE.unlink()
        print(f"✅ 清理完成")

        return str(MODEL_FILE)

    except Exception as e:
        print(f"❌ 下载失败: {e}")
        print(f"   请手动下载: {MODEL_URL}")
        print(f"   解压后保存到: {MODEL_FILE}")
        raise

if __name__ == "__main__":
    model_path = download_model()
    print(f"\n🎉 完成！模型文件路径: {model_path}")