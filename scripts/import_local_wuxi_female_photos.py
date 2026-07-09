#!/usr/bin/env python3
"""Import local Chinese women photos for Wuxi female profiles aged 23-33."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pymysql
from minio import Minio
from minio.error import S3Error
from PIL import Image, ImageEnhance


REPO_ROOT = Path(__file__).resolve().parents[1]
TMP_ROOT = REPO_ROOT / "tmp" / "local-photo-import"
MANIFEST_PATH = TMP_ROOT / "selected_assets.json"
DEFAULT_INPUT_DIR = Path("/Users/sunmuchao/Downloads/test_faces_chinese_women")
MANUAL_EXCLUDE_FILENAMES = {
    "bing_00654.jpg",
    "bing_00029.jpg",
}

VARIANT_SPECS = [
    ("avatar", 640, 800, 1.00, 0.00, 1.00),
    ("gallery_1", 720, 960, 1.06, -0.02, 1.02),
    ("gallery_2", 768, 1024, 1.10, 0.03, 0.98),
    ("gallery_3", 800, 1100, 1.15, 0.00, 1.04),
    ("gallery_4", 720, 1080, 1.18, -0.03, 0.97),
    ("gallery_5", 828, 1170, 1.22, 0.02, 1.01),
]


@dataclass
class LocalAsset:
    source_path: str
    score: float
    uploaded_urls: list[str]


def load_env_file() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def mysql_connection() -> pymysql.Connection:
    return pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", "3307")),
        user=os.environ.get("MYSQL_USER", "root"),
        password=os.environ["MYSQL_ROOT_PASSWORD"],
        database="her",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def minio_client() -> tuple[Minio, str]:
    endpoint = os.environ.get("MINIO_ENDPOINT", "127.0.0.1:9000")
    client = Minio(
        endpoint,
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=str(os.environ.get("MINIO_SECURE", "false")).lower() in {"1", "true", "yes"},
    )
    bucket = os.environ.get("MINIO_BUCKET", "her-media")
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
    except S3Error as exc:
        raise RuntimeError(f"minio bucket check failed: {exc}") from exc
    return client, bucket


def image_files(input_dir: Path) -> list[Path]:
    return sorted(
        [
            path
            for path in input_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        ]
    )


def dhash(image: Image.Image, hash_size: int = 8) -> str:
    gray = image.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
    pixels = np.asarray(gray, dtype=np.int16)
    diff = pixels[:, 1:] > pixels[:, :-1]
    bits = "".join("1" if item else "0" for item in diff.flatten())
    width = 4
    return "".join(f"{int(bits[i:i+width], 2):x}" for i in range(0, len(bits), width))


def hamming_distance(hash_a: str, hash_b: str) -> int:
    a = int(hash_a, 16)
    b = int(hash_b, 16)
    return bin(a ^ b).count("1")


def build_variant_image(image: Image.Image, width: int, height: int, zoom: float, x_shift: float, brightness: float) -> bytes:
    src_w, src_h = image.size
    crop_w = int(src_w / zoom)
    crop_h = int(src_h / zoom)
    crop_w = max(512, min(src_w, crop_w))
    crop_h = max(640, min(src_h, crop_h))
    left = int((src_w - crop_w) / 2 + x_shift * src_w)
    top = int((src_h - crop_h) / 2 - 0.02 * src_h)
    left = max(0, min(src_w - crop_w, left))
    top = max(0, min(src_h - crop_h, top))
    cropped = image.crop((left, top, left + crop_w, top + crop_h)).resize((width, height), Image.Resampling.LANCZOS)
    if abs(brightness - 1.0) > 0.01:
        cropped = ImageEnhance.Brightness(cropped).enhance(brightness)
    out = io.BytesIO()
    cropped.save(out, format="JPEG", quality=92, optimize=True)
    return out.getvalue()


def upload_image_bytes(client: Minio, bucket: str, object_key: str, payload: bytes) -> str:
    client.put_object(bucket, object_key, io.BytesIO(payload), len(payload), content_type="image/jpeg")
    return f"http://minio:9000/{bucket}/{object_key}"


def evaluate_image(path: Path, face_cascade: cv2.CascadeClassifier, eye_cascade: cv2.CascadeClassifier) -> tuple[float, dict[str, Any]] | None:
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        return None
    height, width = image.shape[:2]
    if min(width, height) < 320:
        return None

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))
    if len(faces) != 1:
        return None

    x, y, w, h = max(faces, key=lambda item: item[2] * item[3])
    face_ratio = (w * h) / float(width * height)
    if face_ratio < 0.08:
        return None

    center_x = (x + w / 2) / width
    center_y = (y + h / 2) / height
    if abs(center_x - 0.5) > 0.23 or abs(center_y - 0.42) > 0.25:
        return None

    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
    if blur_score < 50:
        return None

    face_gray = gray[y : y + h, x : x + w]
    eyes = eye_cascade.detectMultiScale(face_gray, scaleFactor=1.1, minNeighbors=4, minSize=(18, 18))
    eye_bonus = min(len(eyes), 2) * 8.0

    brightness = float(np.mean(face_gray)) / 255.0
    if brightness < 0.20 or brightness > 0.92:
        return None

    score = face_ratio * 320 + min(blur_score, 400) * 0.12 + eye_bonus - abs(center_x - 0.5) * 40
    return score, {
        "face_ratio": face_ratio,
        "blur_score": blur_score,
        "center_x": center_x,
        "center_y": center_y,
        "brightness": brightness,
        "eyes": len(eyes),
    }


def select_assets(input_dir: Path, limit: int | None) -> list[Path]:
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")
    candidates: list[tuple[float, str, Path]] = []
    dedupe_hashes: list[str] = []

    for path in image_files(input_dir):
        if path.name in MANUAL_EXCLUDE_FILENAMES:
            continue
        try:
            pil_image = Image.open(path).convert("RGB")
        except Exception:
            continue
        score_result = evaluate_image(path, face_cascade, eye_cascade)
        if score_result is None:
            continue
        score, _meta = score_result
        image_hash = dhash(pil_image)
        if any(hamming_distance(image_hash, seen_hash) <= 6 for seen_hash in dedupe_hashes):
            continue
        dedupe_hashes.append(image_hash)
        candidates.append((score, image_hash, path))

    candidates.sort(key=lambda item: item[0], reverse=True)
    selected = [item[2] for item in candidates]
    if limit and limit > 0:
        selected = selected[:limit]
    return selected


def build_asset_pool(selected_paths: list[Path], *, force_rebuild: bool = False) -> list[LocalAsset]:
    if MANIFEST_PATH.exists() and not force_rebuild:
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        return [
            LocalAsset(
                source_path=str(item["source_path"]),
                score=float(item["score"]),
                uploaded_urls=list(item["uploaded_urls"]),
            )
            for item in payload.get("assets") or []
        ]

    client, bucket = minio_client()
    assets: list[LocalAsset] = []
    TMP_ROOT.mkdir(parents=True, exist_ok=True)

    for idx, path in enumerate(selected_paths):
        image = Image.open(path).convert("RGB")
        base_score = float(1000 - idx)
        uploaded_urls: list[str] = []
        for variant_name, width, height, zoom, x_shift, brightness in VARIANT_SPECS:
            variant_bytes = build_variant_image(image, width, height, zoom, x_shift, brightness)
            object_key = f"virtual-profiles/local-wuxi-female/{path.stem}/{variant_name}-{uuid.uuid4().hex[:10]}.jpg"
            uploaded_urls.append(upload_image_bytes(client, bucket, object_key, variant_bytes))
        assets.append(LocalAsset(source_path=str(path), score=base_score, uploaded_urls=uploaded_urls))

    MANIFEST_PATH.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "source_path": item.source_path,
                        "score": item.score,
                        "uploaded_urls": item.uploaded_urls,
                    }
                    for item in assets
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return assets


def query_target_profiles(limit: int | None) -> list[dict[str, Any]]:
    conn = mysql_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
            SELECT id, name, age, job, photo_count
            FROM profiles
            WHERE city = '无锡'
              AND gender = 'female'
              AND age BETWEEN 23 AND 33
            ORDER BY id ASC
            """
            if limit and limit > 0:
                sql += f" LIMIT {int(limit)}"
            cursor.execute(sql)
            return list(cursor.fetchall())
    finally:
        conn.close()


def choose_asset(profile: dict[str, Any], assets: list[LocalAsset]) -> LocalAsset:
    seed = hashlib.sha256(f"{profile['id']}|{profile.get('age')}|{profile.get('job') or ''}".encode("utf-8")).hexdigest()
    return assets[int(seed[:8], 16) % len(assets)]


def replace_profile_photos(profiles: list[dict[str, Any]], assets: list[LocalAsset]) -> int:
    conn = mysql_connection()
    updated = 0
    try:
        with conn.cursor() as cursor:
            for profile in profiles:
                asset = choose_asset(profile, assets)
                photo_count = int(profile.get("photo_count") or 4)
                photo_count = max(3, min(photo_count, len(asset.uploaded_urls) - 1))
                avatar_url = asset.uploaded_urls[0]
                gallery_urls = asset.uploaded_urls[1 : 1 + photo_count]

                cursor.execute(
                    "UPDATE profiles SET avatar_url=%s, photo_count=%s WHERE id=%s",
                    (avatar_url, len(gallery_urls), int(profile["id"])),
                )
                cursor.execute("DELETE FROM profile_photos WHERE profile_id=%s", (int(profile["id"]),))
                for idx, url in enumerate(gallery_urls):
                    cursor.execute(
                        """
                        INSERT INTO profile_photos (profile_id, photo_url, is_primary, sort_order)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (int(profile["id"]), url, 1 if idx == 0 else 0, idx),
                    )
                updated += 1
        conn.commit()
        return updated
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import local Chinese women photos for Wuxi female profiles aged 23-33")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR), help="Directory containing local photos.")
    parser.add_argument("--select-limit", type=int, default=320, help="Max number of selected source images after filtering.")
    parser.add_argument("--profile-limit", type=int, default=None, help="Only update the first N matched profiles.")
    parser.add_argument("--build-only", action="store_true", help="Only build the selected asset manifest.")
    parser.add_argument("--force-rebuild", action="store_true", help="Rebuild selected assets and MinIO uploads.")
    return parser.parse_args()


def main() -> None:
    load_env_file()
    args = parse_args()
    input_dir = Path(args.input_dir).expanduser().resolve()
    selected = select_assets(input_dir, limit=args.select_limit)
    print(f"Selected {len(selected)} source images from {input_dir}")
    assets = build_asset_pool(selected, force_rebuild=args.force_rebuild)
    print(f"Prepared {len(assets)} uploaded asset pools")
    if args.build_only:
        return
    profiles = query_target_profiles(limit=args.profile_limit)
    updated = replace_profile_photos(profiles, assets)
    print(f"Updated {updated} profiles")


if __name__ == "__main__":
    main()
