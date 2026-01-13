# -------------------------
# HTML 图片本地化
# -------------------------
import base64
import io
import re
import uuid
from typing import TextIO
from urllib.parse import urlparse

import requests
from django.core.files.base import ContentFile
from lxml import html as lxml_html

from dcrm.models import Attachment
from dcrm.models.utils import get_file_mime

try:
    from markdown import markdown as md_to_html  # type: ignore
except Exception:  # pragma: no cover
    md_to_html = None  # type: ignore


def convert_markdown(text: str) -> tuple[str, str]:
    """将 Markdown 文本转换为 HTML，同时返回原始 Markdown 文本。
    """
    if md_to_html is None:
        raise ImportError("markdown 库未安装，请在 requirements.txt 中添加 markdown")
    html: str = md_to_html(
        text,
        extensions=[
            "extra",
            "sane_lists",
            "toc",
        ],
        output_format="html5",
    )
    return html, text


def guess_title_from_markdown(md_text: str) -> str | None:
    """从 Markdown 文本中猜测标题（优先使用第一个 # 开头的行，次选第一行非空文本）。
    """
    for line in md_text.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        if candidate.startswith("#"):
            return candidate.lstrip("#").strip()
        return candidate
    return None


def guess_title_from_html(html: str) -> str | None:
    """从 HTML 中提取第一个 h1-h3 的内容作为标题。
    """
    match = re.search(r"<h[1-3][^>]*>(.*?)</h[1-3]>", html, re.I | re.S)
    if match:
        # 去除可能存在的 HTML 标签
        text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        return text or None
    return None


def convert_docx(file_obj: TextIO) -> tuple[str, str]:
    """将 DOCX 文件对象转换为 HTML，同时返回提取的纯文本作为原始内容。
    """
    try:
        import mammoth  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise ImportError(
            "mammoth 库未安装，请在 requirements.txt 中添加 mammoth"
        ) from exc

    # convert_to_html 会读取文件流，之后需要 seek(0) 再做文本提取
    result_html = mammoth.convert_to_html(file_obj)
    html: str = result_html.value or ""
    file_obj.seek(0)
    result_text = mammoth.extract_raw_text(file_obj)
    raw_text: str = result_text.value or ""
    return html, raw_text


_MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/svg+xml": "svg",
}


def _ext_from_mime(mime: str) -> str:
    return _MIME_TO_EXT.get(mime.lower(), "bin")


def _save_bytes_as_attachment(
    user, data_center, data: bytes, content_type_hint: str | None = None
) -> Attachment:
    # 猜测mime
    mime = content_type_hint or get_file_mime(data, buffer=True)
    ext = _ext_from_mime(mime)
    filename = f"image-{uuid.uuid4().hex}.{ext}"
    attachment = Attachment(
        data_center=data_center,
        created_by=user,
        name=filename,
        mime_type=mime or "unknown",
    )
    attachment.file.save(filename, ContentFile(data), save=True)
    return attachment


def _fetch_remote_bytes(
    url: str, timeout: int = 10, max_size: int = 5 * 1024 * 1024
) -> tuple[bytes | None, str | None]:
    try:
        with requests.get(url, stream=True, timeout=timeout) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type")
            content = io.BytesIO()
            size = 0
            for chunk in resp.iter_content(8192):
                if not chunk:
                    continue
                size += len(chunk)
                if size > max_size:
                    return None, None
                content.write(chunk)
            return content.getvalue(), content_type
    except Exception:
        return None, None


def localize_images_in_html(html: str, user, data_center) -> tuple[str, int]:
    """将 HTML 内的 <img src=...> 转为本地附件，并替换为本地 URL。

    返回 (new_html, count)
    """
    if not html or "<img" not in html.lower():
        return html, 0

    try:
        tree = lxml_html.fromstring(html)
    except Exception:
        # 如果HTML不完整，简单返回原文
        return html, 0

    changed = 0
    for img in tree.xpath("//img[@src]"):
        src = img.get("src") or ""
        if not src:
            continue
        if src.startswith("data:"):
            # data URI: data:[<mime>];base64,<data>
            try:
                header, b64 = src.split(",", 1)
                # 形如 data:image/png;base64
                mime_part = header.split(";")[0]
                mime = mime_part.split(":", 1)[1] if ":" in mime_part else None
                data = base64.b64decode(b64)
                attachment = _save_bytes_as_attachment(user, data_center, data, mime)
                img.set("src", attachment.file.url)
                changed += 1
            except Exception:
                continue
        else:
            # http/https
            parsed = urlparse(src)
            if parsed.scheme in ("http", "https"):
                data, content_type = _fetch_remote_bytes(src)
                if data:
                    attachment = _save_bytes_as_attachment(
                        user, data_center, data, content_type
                    )
                    img.set("src", attachment.file.url)
                    changed += 1
            else:
                # 相对路径等，忽略
                continue

    new_html = lxml_html.tostring(tree, encoding="unicode")
    return new_html, changed
