import logging

import zxingcpp
from PIL import Image

logger = logging.getLogger(__name__)


def extract_barcodes(file_path):
    """只负责图片条码识别，返回条码列表
    Args:
        file_path: 文件路径
    Returns:
        条码信息列表
    """
    try:
        img = Image.open(file_path)
        results = zxingcpp.read_barcodes(img)
        img.close()
        return [
            {
                "type": barcode.format,
                "text": barcode.text,
                "position": barcode.position,
            }
            for barcode in results
        ]
    except Exception as e:
        logger.error(f"条形码识别失败: {str(e)}")
        return []


def extract_ocr_texts(attachment_id, force_ocr=True):
    """只负责OCR识别，返回文本列表
    Args:
        attachment_id: 附件ID
        force_ocr: 是否强制识别
    Returns:
        识别到的文本列表
    """
    pass


def update_attachment_metadata(attachment, barcodes=None, ocr_texts=None):
    """合并识别结果到 metadata 并保存
    Args:
        attachment: 附件对象
        barcodes: 条码信息列表
        ocr_texts: OCR文本列表
    Returns:
        更新后的附件对象
    """
    metadata = attachment.metadata or {}
    if barcodes is not None:
        metadata["barcodes"] = barcodes
    if ocr_texts is not None:
        metadata["ocr_texts"] = ocr_texts
    attachment.metadata = metadata
    attachment.save(update_fields=["metadata"])
    return
