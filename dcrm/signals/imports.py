import logging

from django.dispatch import Signal

logger = logging.getLogger(__name__)

# 定义导入完成信号
# 参数：
#   sender: 模型类
#   instance_ids: 成功导入的实例ID列表
#   user: 导入用户对象
import_completed = Signal()
