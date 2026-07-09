#!/usr/bin/env python3
"""Replace photos for Wuxi female virtual profiles aged 23-33."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymysql
import requests
from minio import Minio
from minio.error import S3Error
from PIL import Image, ImageEnhance


REPO_ROOT = Path(__file__).resolve().parents[1]
TMP_ROOT = REPO_ROOT / "tmp" / "wuxi-female-photo-refresh"
POOL_DIR = TMP_ROOT / "pool"
MANIFEST_PATH = TMP_ROOT / "pool_manifest.json"

DASHSCOPE_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
DASHSCOPE_TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
MODEL_NAME = "wanx2.1-t2i-turbo"

STYLE_PRESETS = [
    ("plain", "素人感，轻微皮肤纹理，淡妆或接近素颜，不过度精致"),
    ("clean", "清爽自然，轻妆，像认真交友软件头像，不过分惊艳"),
    ("gentle", "温柔亲和，笑容自然，生活化，不像棚拍模特"),
    ("bright", "明亮元气，精神状态好，但保留普通真人感"),
    ("professional", "都市通勤感，知性自然，不强烈摆拍，不像网红"),
    ("soft", "柔和甜感，但不过度幼态，不网红滤镜，五官不要过分完美"),
]

VARIANT_SPECS = [
    ("avatar", 640, 800, 1.00, 0.00, 1.00),
    ("gallery_1", 720, 960, 1.07, -0.02, 1.02),
    ("gallery_2", 768, 1024, 1.10, 0.02, 0.98),
    ("gallery_3", 800, 1100, 1.14, 0.00, 1.04),
    ("gallery_4", 720, 1080, 1.18, -0.03, 0.97),
    ("gallery_5", 828, 1170, 1.22, 0.03, 1.01),
]


@dataclass
class GeneratedAsset:
    age: int
    style: str
    source_path: str
    prompt: str
    remote_url: str
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


def build_prompt(age: int, style_hint: str) -> str:
    return (
        f"一位{age}岁中国女性，真实感高清半身人像，正脸直视镜头，单人，"
        "面部占画面60%以上，五官清晰，眼神自然，黑发，肤色自然，"
        "没有男性特征，没有侧脸，没有遮挡，没有多余肢体，没有文字水印，"
        "浅色干净背景，交友资料头像风格，手机或轻单反真实拍摄感，"
        "不要明星脸，不要网红脸，不要过度磨皮，不要过分精致，不要高奢时尚大片感，"
        "允许普通素人长相，允许轻微黑眼圈、轻微皮肤纹理、轻微脸型差异，"
        "不同脸型、不同鼻型、不同唇形、不同妆感，整体像真实资料库用户，"
        f"{style_hint}"
    )


def submit_generation(api_key: str, prompt: str) -> str:
    response = requests.post(
        DASHSCOPE_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        },
        json={
            "model": MODEL_NAME,
            "input": {"prompt": prompt},
            "parameters": {"size": "1024*1024", "n": 1},
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    task_id = ((payload.get("output") or {}).get("task_id") or "").strip()
    if not task_id:
        raise RuntimeError(f"generation task missing task_id: {payload}")
    return task_id


def poll_generation(api_key: str, task_id: str) -> str:
    for _ in range(40):
        response = requests.get(
            DASHSCOPE_TASK_URL.format(task_id=task_id),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        output = payload.get("output") or {}
        status = str(output.get("task_status") or "").upper()
        if status == "SUCCEEDED":
            results = output.get("results") or []
            if not results or not results[0].get("url"):
                raise RuntimeError(f"generation succeeded without result url: {payload}")
            return str(results[0]["url"])
        if status in {"FAILED", "CANCELED"}:
            raise RuntimeError(f"generation failed: {payload}")
        time.sleep(3)
    raise TimeoutError(f"generation timed out: {task_id}")


def download_image(url: str) -> bytes:
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    return response.content


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
    cropped = image.crop((left, top, left + crop_w, top + crop_h)).resize((width, height), Image.LANCZOS)
    if abs(brightness - 1.0) > 0.01:
        cropped = ImageEnhance.Brightness(cropped).enhance(brightness)
    out = io.BytesIO()
    cropped.save(out, format="JPEG", quality=92, optimize=True)
    return out.getvalue()


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


def upload_image_bytes(client: Minio, bucket: str, object_key: str, payload: bytes) -> str:
    client.put_object(
        bucket,
        object_key,
        io.BytesIO(payload),
        len(payload),
        content_type="image/jpeg",
    )
    return f"http://minio:9000/{bucket}/{object_key}"


def load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {"assets": []}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def save_manifest(payload: dict[str, Any]) -> None:
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def collect_existing_source_files() -> dict[tuple[int, str], Path]:
    out: dict[tuple[int, str], Path] = {}
    if not POOL_DIR.exists():
        return out
    for path in POOL_DIR.glob("wuxi_female_*_*.jpg"):
        stem = path.stem
        parts = stem.split("_")
        if len(parts) < 4:
            continue
        try:
            age = int(parts[2])
        except ValueError:
            continue
        style = "_".join(parts[3:])
        out[(age, style)] = path
    return out


def ensure_asset_pool(api_key: str, *, force_regenerate: bool = False) -> list[GeneratedAsset]:
    manifest = load_manifest()
    existing_assets: list[GeneratedAsset] = []
    if not force_regenerate:
        for item in manifest.get("assets") or []:
            uploaded_urls = list(item.get("uploaded_urls") or [])
            if len(uploaded_urls) >= len(VARIANT_SPECS):
                existing_assets.append(
                    GeneratedAsset(
                        age=int(item["age"]),
                        style=str(item["style"]),
                        source_path=str(item["source_path"]),
                        prompt=str(item["prompt"]),
                        remote_url=str(item["remote_url"]),
                        uploaded_urls=uploaded_urls,
                    )
                )
        if existing_assets:
            return existing_assets

    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    POOL_DIR.mkdir(parents=True, exist_ok=True)
    client, bucket = minio_client()
    built_assets: list[GeneratedAsset] = []
    local_sources = {} if force_regenerate else collect_existing_source_files()

    for age in range(23, 34):
        for style_name, style_hint in STYLE_PRESETS:
            prompt = build_prompt(age, style_hint)
            source_name = f"wuxi_female_{age}_{style_name}.jpg"
            source_path = POOL_DIR / source_name
            remote_url = ""

            existing_path = local_sources.get((age, style_name))
            if existing_path and existing_path.exists():
                image_bytes = existing_path.read_bytes()
                source_path = existing_path
            else:
                task_id = submit_generation(api_key, prompt)
                remote_url = poll_generation(api_key, task_id)
                image_bytes = download_image(remote_url)
                source_path.write_bytes(image_bytes)

            source_path.write_bytes(image_bytes)
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            uploaded_urls: list[str] = []
            for variant_name, width, height, zoom, x_shift, brightness in VARIANT_SPECS:
                variant_bytes = build_variant_image(image, width, height, zoom, x_shift, brightness)
                object_key = (
                    f"virtual-profiles/wuxi-female-23-33/age-{age}/{style_name}/"
                    f"{variant_name}-{uuid.uuid4().hex[:10]}.jpg"
                )
                uploaded_urls.append(upload_image_bytes(client, bucket, object_key, variant_bytes))
            built_assets.append(
                GeneratedAsset(
                    age=age,
                    style=style_name,
                    source_path=str(source_path),
                    prompt=prompt,
                    remote_url=remote_url,
                    uploaded_urls=uploaded_urls,
                )
            )

    save_manifest(
        {
            "assets": [
                {
                    "age": item.age,
                    "style": item.style,
                    "source_path": item.source_path,
                    "prompt": item.prompt,
                    "remote_url": item.remote_url,
                    "uploaded_urls": item.uploaded_urls,
                }
                for item in built_assets
            ]
        }
    )
    return built_assets


def query_target_profiles(limit: int | None) -> list[dict[str, Any]]:
    conn = mysql_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
            SELECT id, name, age, city, gender, job, photo_count
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


def choose_asset(profile: dict[str, Any], assets_by_age: dict[int, list[GeneratedAsset]]) -> GeneratedAsset:
    age = int(profile["age"])
    pool = assets_by_age[age]
    seed = hashlib.sha256(f"{profile['id']}|{profile.get('job') or ''}".encode("utf-8")).hexdigest()
    index = int(seed[:8], 16) % len(pool)
    return pool[index]


def replace_profile_photos(profiles: list[dict[str, Any]], assets: list[GeneratedAsset]) -> int:
    assets_by_age: dict[int, list[GeneratedAsset]] = {}
    for asset in assets:
        assets_by_age.setdefault(asset.age, []).append(asset)

    conn = mysql_connection()
    updated = 0
    try:
        with conn.cursor() as cursor:
            for profile in profiles:
                asset = choose_asset(profile, assets_by_age)
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
    parser = argparse.ArgumentParser(description="Replace Wuxi female 23-33 profile photos")
    parser.add_argument("--limit", type=int, default=None, help="Only update the first N matched profiles.")
    parser.add_argument("--skip-generate", action="store_true", help="Reuse existing pool manifest only.")
    parser.add_argument("--force-regenerate", action="store_true", help="Ignore old pool and regenerate images.")
    parser.add_argument("--generate-only", action="store_true", help="Only build the image pool, do not update DB.")
    return parser.parse_args()


def main() -> None:
    load_env_file()
    args = parse_args()
    api_key = (os.environ.get("DASHSCOPE_API_KEY") or "").strip()
    if not api_key and not args.skip_generate:
        raise RuntimeError("DASHSCOPE_API_KEY is required")

    profiles = query_target_profiles(limit=args.limit)
    if not profiles:
        print("No target profiles matched.")
        return

    if args.skip_generate and not MANIFEST_PATH.exists():
        raise RuntimeError("--skip-generate requires an existing manifest")

    assets = (
        ensure_asset_pool(api_key, force_regenerate=args.force_regenerate)
        if not args.skip_generate
        else ensure_asset_pool(api_key="", force_regenerate=False)
    )
    if args.generate_only:
        print(f"Generated or resumed {len(assets)} pooled assets.")
        return

    updated = replace_profile_photos(profiles, assets)
    print(f"Updated {updated} profiles.")


if __name__ == "__main__":
    main()
