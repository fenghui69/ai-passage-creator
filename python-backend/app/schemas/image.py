"""图片相关数据模型"""

import base64
import re
from typing import List, Optional, Tuple
from enum import Enum
from pydantic import BaseModel, Field


# MIME 类型与文件扩展名映射
_EXTENSION_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
    "image/svg+xml": ".svg",
}


def extension_for_mime(mime_type: Optional[str]) -> str:
    """根据 MIME 类型获取文件扩展名，未知类型回退 .png"""
    if not mime_type:
        return ".png"
    return _EXTENSION_BY_MIME.get(mime_type.lower(), ".png")


def sniff_image_mime_type(data: Optional[bytes]) -> Optional[str]:
    """
    根据文件头判断图片的真实 MIME 类型

    图片 URL 往往无法反映真实格式（例如 Iconify 返回的 .svg 图标），
    以字节内容为准才能避免 Content-Type 标错导致浏览器拒绝渲染。

    Args:
        data: 图片字节数据

    Returns:
        识别出的 MIME 类型，无法识别返回 None
    """
    if not data:
        return None

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"BM"):
        return "image/bmp"
    if data.startswith(b"\x00\x00\x01\x00"):
        return "image/x-icon"

    # SVG：可能是裸 <svg>、带 XML 声明，或带 UTF-8 BOM / 前导空白
    head = data[:1024]
    stripped = head.lstrip(b"\xef\xbb\xbf").lstrip()
    if stripped[:4].lower() == b"<svg":
        return "image/svg+xml"
    if stripped[:5].lower() == b"<?xml" and b"<svg" in head.lower():
        return "image/svg+xml"

    return None


# SVG 中可携带主动内容的元素（含 <script>、<foreignObject> 及各类嵌入标签）
_SVG_DANGEROUS_ELEMENT = re.compile(
    r"<\s*(script|foreignObject|iframe|embed|object)\b[^>]*?(?:/\s*>|>.*?</\s*\1\s*>)",
    re.IGNORECASE | re.DOTALL,
)
# 兜底清理上一步遗漏的孤立/未闭合标签
_SVG_LEFTOVER_TAG = re.compile(
    r"<\s*/?\s*(script|foreignObject|iframe|embed|object)\b[^>]*>",
    re.IGNORECASE,
)
# 事件属性，如 onload="..."、onclick='...'
_SVG_EVENT_ATTRIBUTE = re.compile(
    r"""\son[a-z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""",
    re.IGNORECASE,
)
# 伪协议链接，如 href="javascript:..."
_SVG_SCRIPT_URI = re.compile(
    r"""((?:xlink:href|href|src)\s*=\s*)(["'])\s*(?:javascript|vbscript|data:text/html)[^"']*\2""",
    re.IGNORECASE,
)


def sanitize_svg(data: Optional[bytes]) -> Tuple[Optional[bytes], List[str]]:
    """
    移除 SVG 中的主动内容（脚本、事件属性、伪协议链接）

    SVG 直接访问时（而非通过 <img> 加载）其中携带的脚本会在托管域名下执行。
    本项目的配图最终都渲染为 Markdown 的 `![](url)`，即 <img> 上下文，脚本本来
    就不会执行；此处的清理属于纵深防御，用于覆盖「用户直接打开图片链接」的情况，
    不替代对 SVG 来源的信任控制。

    Args:
        data: SVG 字节数据

    Returns:
        (清理后的字节, 被移除项的描述列表)。无需修改时原样返回且列表为空
    """
    if not data:
        return data, []

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        # 无法按文本处理（且 sniff_image_mime_type 也不会把这类内容识别成 SVG）
        return data, []

    removed: List[str] = []

    text, count = _SVG_DANGEROUS_ELEMENT.subn("", text)
    if count:
        removed.append(f"危险元素 x{count}")

    text, count = _SVG_LEFTOVER_TAG.subn("", text)
    if count:
        removed.append(f"残留标签 x{count}")

    text, count = _SVG_EVENT_ATTRIBUTE.subn("", text)
    if count:
        removed.append(f"事件属性 x{count}")

    text, count = _SVG_SCRIPT_URI.subn(r"\1\2#\2", text)
    if count:
        removed.append(f"伪协议链接 x{count}")

    if not removed:
        return data, []

    return text.encode("utf-8"), removed


class ImageRequest(BaseModel):
    """图片请求对象"""
    
    keywords: Optional[str] = Field(None, description="搜索关键词（用于图库检索）")
    prompt: Optional[str] = Field(None, description="生图提示词（用于 AI 生图）")
    position: Optional[int] = Field(None, description="图片位置序号")
    type: Optional[str] = Field(None, description="图片类型（cover/section）")
    aspect_ratio: Optional[str] = Field(None, description="宽高比（如 16:9, 1:1）")
    style: Optional[str] = Field(None, description="图片风格描述")
    
    def get_effective_param(self, is_ai_generated: bool) -> str:
        """
        获取有效的搜索/生成参数
        AI 生图优先使用 prompt，图库检索使用 keywords
        """
        if is_ai_generated:
            return self.prompt if self.prompt else self.keywords or ""
        return self.keywords if self.keywords else self.prompt or ""


class DataType(str, Enum):
    """数据类型枚举"""
    
    BYTES = "BYTES"
    URL = "URL"
    DATA_URL = "DATA_URL"


class ImageData:
    """
    图片数据封装类
    用于统一处理不同来源的图片数据（字节、URL、base64 等）
    """
    
    def __init__(
        self,
        bytes_data: Optional[bytes] = None,
        url: Optional[str] = None,
        mime_type: Optional[str] = None,
        data_type: Optional[DataType] = None
    ):
        self.bytes = bytes_data
        self.url = url
        self.mime_type = mime_type or "image/png"
        self.data_type = data_type
    
    @classmethod
    def from_url(cls, url: Optional[str]) -> Optional["ImageData"]:
        """从外部 URL 创建 ImageData"""
        if not url:
            return None
        
        # 判断是否为 base64 data URL
        if url.startswith("data:"):
            return cls.from_data_url(url)
        
        return cls(url=url, data_type=DataType.URL)
    
    @classmethod
    def from_data_url(cls, data_url: str) -> Optional["ImageData"]:
        """从 base64 data URL 创建 ImageData"""
        if not data_url or not data_url.startswith("data:"):
            return None
        
        # 解析 data URL 格式: data:image/png;base64,xxxxx
        mime_type = "image/png"
        mime_end = data_url.find(";")
        if mime_end > 5:
            mime_type = data_url[5:mime_end]
        
        return cls(url=data_url, mime_type=mime_type, data_type=DataType.DATA_URL)
    
    @classmethod
    def from_bytes(cls, bytes_data: bytes, mime_type: str = "image/png") -> Optional["ImageData"]:
        """从字节数据创建 ImageData"""
        if not bytes_data:
            return None
        
        return cls(bytes_data=bytes_data, mime_type=mime_type, data_type=DataType.BYTES)
    
    def get_image_bytes(self) -> Optional[bytes]:
        """获取图片字节数据（如果是 data URL，会解码 base64）"""
        if self.data_type == DataType.BYTES:
            return self.bytes
        
        if self.data_type == DataType.DATA_URL and self.url:
            # 解析 base64 data URL
            base64_start = self.url.find(",")
            if base64_start > 0:
                base64_data = self.url[base64_start + 1:]
                return base64.b64decode(base64_data)
        
        return None
    
    def is_valid(self) -> bool:
        """判断是否有有效数据"""
        if self.data_type == DataType.BYTES:
            return self.bytes is not None and len(self.bytes) > 0
        elif self.data_type in [DataType.URL, DataType.DATA_URL]:
            return self.url is not None and len(self.url) > 0
        return False
    
    def get_file_extension(self) -> str:
        """根据 MIME 类型获取文件扩展名"""
        return extension_for_mime(self.mime_type)
