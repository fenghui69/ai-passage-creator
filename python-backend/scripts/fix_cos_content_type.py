"""存量 COS 对象 Content-Type 修正脚本

背景
----
早期版本把「URL 来源」的图片一律按 image/png 处理：`ImageData.from_url()` 不做格式探测，
`mime_type` 兜底为 image/png，于是 Iconify 返回的 SVG 图标被以 `iconify/<uuid>.png`
为键、`Content-Type: image/png` 为元数据上传到 COS。

Chrome 会嗅探光栅格式（JPEG/WebP/GIF 内容即使标成 image/png 也能渲染），但**不嗅探 SVG**
——只有明确声明为 `image/svg+xml` 时 `<img>` 才会渲染。这就是页面上图标显示为裂图的原因。

本脚本扫描 article 表中引用到的 COS 图片，按文件头判断真实格式，对 Content-Type
不符的对象**原地修正元数据**：URL 不变、对象内容不变、数据库无需改动。

用法（在 python-backend 目录下执行）
------------------------------------
    python scripts/fix_cos_content_type.py                    # 预演，只打印将要修正的对象
    python scripts/fix_cos_content_type.py --apply            # 实际执行修正
    python scripts/fix_cos_content_type.py --apply --prefix iconify/   # 只处理指定前缀
"""

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import unquote, urlparse

# 允许以 `python scripts/fix_cos_content_type.py` 方式直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qcloud_cos import CosConfig, CosS3Client  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.schemas.image import sniff_image_mime_type  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("fix_cos_content_type")
# COS SDK 会为每个请求打两条 INFO 日志，扫描大量对象时刷屏
logging.getLogger("qcloud_cos").setLevel(logging.WARNING)

# 从 Markdown 链接 / HTML src / JSON 字段中提取 URL
URL_PATTERN = re.compile(r"https?://[^\s\)\]\"'<>\\]+")

# 判断真实格式只需读取文件头
SNIFF_BYTES = 4096

# 需要扫描的 article 表列
SCANNED_COLUMNS = ["fullContent", "content", "coverImage", "images"]


def build_client() -> CosS3Client:
    """初始化 COS 客户端（复用后端配置）"""
    config = CosConfig(
        Region=settings.tencent_cos_region,
        SecretId=settings.tencent_cos_secret_id,
        SecretKey=settings.tencent_cos_secret_key,
        Scheme="https",
    )
    return CosS3Client(config)


def collect_object_keys() -> Set[str]:
    """扫描 article 表，收集所有被引用到的 COS 对象键"""
    columns = ", ".join(f"`{column}`" for column in SCANNED_COLUMNS)
    session = SessionLocal()
    try:
        rows = session.execute(text(f"SELECT {columns} FROM article")).fetchall()
    finally:
        session.close()

    keys: Set[str] = set()
    for row in rows:
        for value in row:
            if not value:
                continue
            for url in URL_PATTERN.findall(str(value)):
                key = extract_object_key(url)
                if key:
                    keys.add(key)

    logger.info(f"从数据库中收集到 {len(keys)} 个去重后的 COS 对象")
    return keys


def extract_object_key(url: str) -> Optional[str]:
    """从 COS 访问 URL 中提取对象键，非 COS 地址返回 None"""
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    # 默认域名 <bucket>.cos.<region>.myqcloud.com，或配置的自定义域名
    custom_domain = (settings.tencent_cos_domain or "").lower().replace("https://", "").replace("http://", "")
    is_cos = host.endswith(".myqcloud.com") or (custom_domain and host == custom_domain)
    if not is_cos:
        return None

    key = unquote(parsed.path.lstrip("/"))
    return key or None


def fetch_head(client: CosS3Client, bucket: str, key: str) -> Optional[Dict]:
    """获取对象元信息，不存在或无权限时返回 None"""
    try:
        return client.head_object(Bucket=bucket, Key=key)
    except Exception as e:  # noqa: BLE001 - SDK 异常类型较杂，统一降级处理
        logger.warning(f"读取对象元信息失败, key={key}, error={e}")
        return None


def fetch_head_bytes(client: CosS3Client, bucket: str, key: str) -> Optional[bytes]:
    """读取对象开头若干字节用于格式探测"""
    try:
        response = client.get_object(
            Bucket=bucket, Key=key, Range=f"bytes=0-{SNIFF_BYTES - 1}"
        )
        return response["Body"].get_raw_stream().read()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"读取对象内容失败, key={key}, error={e}")
        return None


def replace_content_type(client: CosS3Client, bucket: str, key: str, mime_type: str) -> bool:
    """原地修正对象的 Content-Type（CopyStatus='Replaced' 表示重写元数据）"""
    try:
        client.copy_object(
            Bucket=bucket,
            Key=key,
            CopySource={
                "Bucket": bucket,
                "Region": settings.tencent_cos_region,
                "Key": key,
            },
            CopyStatus="Replaced",
            ContentType=mime_type,
        )
        return True
    except Exception as e:  # noqa: BLE001
        logger.error(f"修正 Content-Type 失败, key={key}, mime={mime_type}, error={e}")
        return False


def scan(
    client: CosS3Client,
    bucket: str,
    keys: List[str],
) -> Tuple[List[Tuple[str, str, str]], List[str]]:
    """
    逐个探测对象的真实格式

    Returns:
        (待修正列表 [(key, 当前 Content-Type, 真实 MIME)], 读取失败的对象键)
    """
    pending: List[Tuple[str, str, str]] = []
    unreadable: List[str] = []

    for key in keys:
        head = fetch_head(client, bucket, key)
        if head is None:
            unreadable.append(key)
            continue

        current_type = (head.get("Content-Type") or "").split(";")[0].strip()

        body = fetch_head_bytes(client, bucket, key)
        if body is None:
            unreadable.append(key)
            continue

        detected = sniff_image_mime_type(body)
        if detected and detected != current_type:
            pending.append((key, current_type or "(空)", detected))

    return pending, unreadable


def main() -> int:
    parser = argparse.ArgumentParser(description="修正 COS 存量图片的 Content-Type")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际执行修正；不加此参数时只做预演（dry-run）",
    )
    parser.add_argument(
        "--prefix",
        default="",
        help="只处理指定对象键前缀，例如 iconify/",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="最多处理多少个对象，0 表示不限制",
    )
    args = parser.parse_args()

    bucket = settings.tencent_cos_bucket
    if not bucket:
        logger.error("未配置 TENCENT_COS_BUCKET，无法继续")
        return 1

    logger.info(f"目标存储桶: {bucket} (region={settings.tencent_cos_region})")
    logger.info("模式: " + ("实际修正 (--apply)" if args.apply else "预演 (dry-run)"))

    keys = sorted(collect_object_keys())
    if args.prefix:
        keys = [key for key in keys if key.startswith(args.prefix)]
        logger.info(f"按前缀 '{args.prefix}' 过滤后剩余 {len(keys)} 个对象")
    if args.limit > 0:
        keys = keys[: args.limit]

    if not keys:
        logger.info("没有需要检查的对象，退出")
        return 0

    client = build_client()
    pending, unreadable = scan(client, bucket, keys)

    print()
    print(f"扫描对象数: {len(keys)}")
    print(f"需要修正  : {len(pending)}")
    print(f"无法读取  : {len(unreadable)}")
    print()

    for key, current_type, detected in pending:
        print(f"  {key}  [{current_type} -> {detected}]")

    if not pending:
        print("所有对象的 Content-Type 均已正确，无需处理。")
        return 0

    if not args.apply:
        print()
        print("以上为预演结果，未做任何修改。确认无误后加 --apply 执行。")
        return 0

    print()
    fixed = 0
    failed = 0
    for key, _current_type, detected in pending:
        if replace_content_type(client, bucket, key, detected):
            fixed += 1
            logger.info(f"已修正: {key} -> {detected}")
        else:
            failed += 1

    print()
    print(f"修正完成: 成功 {fixed}, 失败 {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
