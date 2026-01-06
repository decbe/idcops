import logging
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
from lxml import html

logger = logging.getLogger(__name__)


@dataclass
class IconInfo:
    """图标信息"""

    url: str
    size: int = 0
    type: str = ""
    rel: str = ""
    source: str = ""  # 来源：'meta', 'link', 'img', 'default'
    alt: str = ""  # 图片替代文本


HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "zh-CN,zh;q=0.9",
    "cache-control": "no-cache",
    "dnt": "1",
    "pragma": "no-cache",
    "priority": "u=0, i",
    "sec-ch-ua": '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "sec-gpc": "1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
}


class IconFetcher:
    """图标获取器"""

    TIMEOUT = 60
    VALID_TYPES = {"png", "ico", "jpeg", "jpg", "svg", "gif", "webp"}
    LOGO_PATTERNS = [
        r"logo[._-]?([0-9]+)?\.(png|jpg|jpeg|svg|gif|webp)",
        r"brand[._-]?([0-9]+)?\.(png|jpg|jpeg|svg|gif|webp)",
        r"site[._-]?logo[._-]?([0-9]+)?\.(png|jpg|jpeg|svg|gif|webp)",
    ]
    LOGO_KEYWORDS = {"logo", "site-logo", "company-logo"}

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _extract_size(self, sizes: str) -> int:
        """从 sizes 属性提取尺寸"""
        if not sizes:
            return 0
        try:
            # 处理类似 "32x32" 或 "32" 的格式
            size = sizes.split("x")[0].strip()
            return int(size)
        except (ValueError, IndexError):
            return 0

    def _get_icon_type(self, url: str, type_attr: str = "") -> str:
        """获取图标类型"""
        if type_attr and "/" in type_attr:
            icon_type = type_attr.split("/")[-1]
            if icon_type in self.VALID_TYPES:
                return icon_type

        ext = url.split(".")[-1].lower()
        return ext if ext in self.VALID_TYPES else ""

    def _score_icon(self, icon: IconInfo) -> int:
        """为图标评分"""
        score = 0

        # 根据来源评分
        source_scores = {
            "meta": 100,  # meta 标签最优先
            "link": 80,  # link 标签次之
            "img": 60,  # img 标签再次
            "default": 40,  # 默认图标最后
        }
        score += source_scores.get(icon.source, 0)

        # 根据尺寸评分
        if 32 <= icon.size <= 192:
            score += 100
        elif icon.size > 192:
            score += 50
        elif icon.size > 0:
            score += 25

        # 根据类型评分
        type_scores = {
            "svg": 50,  # SVG 最优先（矢量图）
            "png": 45,
            "webp": 40,
            "ico": 55,
            "gif": 30,
            "jpg": 25,
            "jpeg": 25,
        }
        score += type_scores.get(icon.type, 0)

        # 根据关系评分
        rel_scores = {
            "icon": 30,
            "shortcut icon": 20,
            "apple-touch-icon": 25,
            "apple-touch-icon-precomposed": 15,
        }
        score += rel_scores.get(icon.rel, 0)

        # 根据 alt 文本评分
        if icon.alt and any(
            keyword in icon.alt.lower() for keyword in self.LOGO_KEYWORDS
        ):
            score += 40

        return score

    def _find_meta_icons(self, tree, base_domain: str) -> list[IconInfo]:
        """从 meta 标签查找图标"""
        icons = []

        # 查找所有可能的图标链接
        for link in tree.xpath("//link[@rel]"):
            rel = link.get("rel", "").lower()
            if any(x in rel for x in ["icon", "shortcut icon", "apple-touch-icon"]):
                href = link.get("href")
                if href:
                    if not href.startswith(("http://", "https://", "//")):
                        href = urljoin(base_domain, href.lstrip("/"))

                    if href.startswith("//"):
                        href = "https:" + href

                    icons.append(
                        IconInfo(
                            url=href,
                            size=self._extract_size(link.get("sizes", "")),
                            type=self._get_icon_type(href, link.get("type", "")),
                            rel=rel,
                            source="meta",
                        )
                    )

        return icons

    def get_website_favicon(
        self, website_url: str
    ) -> tuple[str | None, bytes | None]:
        """获取网站图标
        :param website_url: 网站URL
        :return: 图标URL和图标内容

        """
        try:
            if not website_url.startswith(("http://", "https://")):
                website_url = "https://" + website_url

            response = self.session.get(website_url, timeout=self.TIMEOUT, verify=False)
            response.raise_for_status()

            tree = html.fromstring(response.content)
            base_url = urlparse(website_url)
            base_domain = f"{base_url.scheme}://{base_url.netloc}"

            icons = []

            # 1. 从 meta 标签获取图标
            icons.extend(self._find_meta_icons(tree, base_domain))

            # 3. 添加默认的 favicon.ico
            default_icon = urljoin(base_domain, "favicon.ico")
            icons.append(
                IconInfo(
                    url=default_icon, type="ico", rel="shortcut icon", source="default"
                )
            )

            # 按分数排序
            icons.sort(key=self._score_icon, reverse=True)
            # 尝试获取最佳图标
            for icon in icons:
                try:
                    icon_response = self.session.get(
                        icon.url, timeout=self.TIMEOUT, verify=False
                    )
                    if icon_response.status_code == 200:
                        content_type = icon_response.headers.get("content-type", "")
                        if any(x in content_type for x in ["image", "icon"]):
                            # 修改返回文件名和文件类型
                            # file_name = f"favicon.{icon.type}"  # 使用图标类型作为文件名后缀
                            file_name = icon.url.split("/")[-1]
                            logger.info(
                                f"成功获取图标: {icon.url} (来源: {icon.source})"
                            )
                            return (
                                icon.url,
                                file_name,
                                icon_response.content,
                            )  # 返回文件名和内容
                except Exception as e:
                    logger.debug(f"获取图标失败 {icon.url}: {str(e)}")
                    continue

        except Exception as e:
            base_url = urlparse(website_url)
            base_domain = f"{base_url.scheme}://{base_url.netloc}"
            default_icon = urljoin(base_domain, "favicon.ico")
            icon_response = self.session.get(
                default_icon, timeout=self.TIMEOUT, verify=False
            )
            if icon_response.status_code == 200:
                return (
                    default_icon,
                    "favicon.ico",
                    icon_response.content,
                )
            else:
                logger.error(f"获取网站图标失败 {website_url}: {str(e)}")
        return None, None, None


# 创建单例实例
icon_fetcher = IconFetcher()
