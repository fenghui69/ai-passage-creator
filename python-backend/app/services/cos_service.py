"""腾讯云 COS 服务"""

import logging
import httpx
import uuid
from typing import Optional
from qcloud_cos import CosConfig, CosS3Client
from io import BytesIO

from app.config import settings
from app.schemas.image import (
    ImageData,
    DataType,
    extension_for_mime,
    sanitize_svg,
    sniff_image_mime_type,
)

logger = logging.getLogger(__name__)


class CosService:
    """腾讯云 COS 服务"""
    
    def __init__(self):
        # 初始化 COS 客户端
        config = CosConfig(
            Region=settings.tencent_cos_region,
            SecretId=settings.tencent_cos_secret_id,
            SecretKey=settings.tencent_cos_secret_key,
            Scheme='https'
        )
        self.client = CosS3Client(config)
        self.bucket = settings.tencent_cos_bucket
        self.region = settings.tencent_cos_region
        self.http_client = httpx.AsyncClient(timeout=30.0)
    
    async def upload_image(self, image_url: str, folder: str) -> str:
        """
        上传图片到 COS

        Args:
            image_url: 图片 URL
            folder: 文件夹

        Returns:
            COS 图片 URL
        """
        # 统一走 upload_image_data，复用其中的 MIME 探测逻辑
        image_data = ImageData.from_url(image_url)
        cos_url = await self.upload_image_data(image_data, folder) if image_data else None
        # 降级：上传失败时直接返回原始 URL
        return cos_url or image_url

    async def upload_image_data(
        self,
        image_data: ImageData,
        folder: str
    ) -> Optional[str]:
        """
        上传图片数据到 COS（第 5 期新增）
        支持多种数据格式：字节数据、URL、data URL
        
        Args:
            image_data: 图片数据
            folder: 文件夹
            
        Returns:
            COS 图片 URL
        """
        if not image_data or not image_data.is_valid():
            logger.warning("图片数据无效")
            return None
        
        try:
            # 1. 获取图片字节数据
            if image_data.data_type == DataType.BYTES:
                image_bytes = image_data.bytes
            elif image_data.data_type == DataType.DATA_URL:
                image_bytes = image_data.get_image_bytes()
            elif image_data.data_type == DataType.URL:
                # 下载图片
                response = await self.http_client.get(image_data.url)
                if response.status_code != 200:
                    logger.error(f"下载图片失败: {image_data.url}")
                    return image_data.url  # 降级：直接返回原始 URL
                image_bytes = response.content
            else:
                logger.error(f"未知的数据类型: {image_data.data_type}")
                return None
            
            if not image_bytes:
                logger.error("图片字节数据为空")
                return None

            # 2. 以真实文件头为准修正 MIME 类型
            #    URL 来源的图片（如 Iconify 的 .svg 图标）无法从 URL 得知真实格式，
            #    ImageData 会兜底成 image/png，导致 SVG 被标成 PNG 而无法被浏览器渲染
            mime_type = sniff_image_mime_type(image_bytes) or image_data.mime_type or "image/png"
            if mime_type != image_data.mime_type:
                logger.info(f"修正图片 MIME 类型: {image_data.mime_type} -> {mime_type}")

            # 3. SVG 上传前移除主动内容
            #    渲染路径是 <img>，脚本本就不会执行；这里覆盖「直接打开图片链接」的场景
            if mime_type == "image/svg+xml":
                sanitized, removed = sanitize_svg(image_bytes)
                if removed:
                    logger.warning(f"SVG 已清理主动内容: {', '.join(removed)}")
                if sanitized is not None:
                    image_bytes = sanitized

            # 4. 生成文件名
            extension = extension_for_mime(mime_type)
            file_name = f"{folder}/{uuid.uuid4()}{extension}"

            # 5. 上传到 COS
            self.client.put_object(
                Bucket=self.bucket,
                Body=BytesIO(image_bytes),
                Key=file_name,
                ContentType=mime_type
            )
            
            # 6. 返回访问 URL
            cos_url = f"https://{self.bucket}.cos.{self.region}.myqcloud.com/{file_name}"
            logger.info(f"图片上传成功, size={len(image_bytes)} bytes, cosUrl={cos_url}")
            
            return cos_url
        except Exception as e:
            logger.error(f"上传图片数据到 COS 失败: {e}")
            # 如果是 URL 类型，降级返回原始 URL
            if image_data.data_type == DataType.URL:
                return image_data.url
            return None
    
    def use_direct_url(self, image_url: str) -> str:
        """
        直接使用图片 URL（不上传到 COS）
        
        Args:
            image_url: 图片 URL
            
        Returns:
            图片 URL
        """
        return image_url
    
    async def close(self):
        """关闭 HTTP 客户端"""
        await self.http_client.aclose()
