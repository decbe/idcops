import logging
import os

from django.core.management.base import BaseCommand
from django.db.models import Count

from dcrm.models import Attachment

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "验证数据库中的附件文件是否在文件系统中存在"

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            help="自动修复丢失的文件（将删除数据库中不存在对应物理文件的记录）",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="显示详细信息",
        )

    def handle(self, *args, **options):
        fix = options.get("fix", False)
        verbose = options.get("verbose", False)

        self.stdout.write("开始验证附件文件...")
        attachments = Attachment.objects.all()
        total_count = attachments.count()
        missing_files = []
        error_files = []

        # 统计信息
        self.stdout.write(f"数据库中共有 {total_count} 个附件记录")

        for idx, attachment in enumerate(attachments, 1):
            if verbose and idx % 100 == 0:
                self.stdout.write(f"进度: {idx}/{total_count}")

            try:
                file_exists = False
                if hasattr(attachment.file, "path") and attachment.file.path:
                    file_path = attachment.file.path
                    file_exists = os.path.exists(file_path)
                    if not file_exists:
                        missing_files.append(attachment)
                        self.stdout.write(
                            self.style.WARNING(
                                f"文件不存在: ID={attachment.id}, "
                                f"路径={file_path}, "
                                f"md5sum={attachment.md5sum}"
                            )
                        )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"文件路径无效: ID={attachment.id}, "
                            f"md5sum={attachment.md5sum}"
                        )
                    )
                    missing_files.append(attachment)
            except Exception as e:
                error_files.append((attachment, str(e)))
                self.stdout.write(
                    self.style.ERROR(
                        f"检查文件时出错: ID={attachment.id}, 错误={str(e)}"
                    )
                )

        # 输出统计信息
        self.stdout.write("=" * 50)
        self.stdout.write(f"验证完成! 总附件数: {total_count}")
        self.stdout.write(f"丢失文件数: {len(missing_files)}")
        self.stdout.write(f"验证错误数: {len(error_files)}")

        # 如果指定了修复选项，则删除丢失文件的记录
        if fix and missing_files:
            self.stdout.write("开始修复: 删除丢失文件的数据库记录...")
            for attachment in missing_files:
                try:
                    attachment_id = attachment.id
                    attachment.delete()
                    self.stdout.write(
                        self.style.SUCCESS(f"已删除丢失文件的记录: ID={attachment_id}")
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"删除记录时出错: ID={attachment.id}, 错误={str(e)}"
                        )
                    )

            self.stdout.write(
                self.style.SUCCESS(f"修复完成，已删除 {len(missing_files)} 条记录")
            )

        # 详细错误信息
        if error_files and verbose:
            self.stdout.write("\n详细错误信息:")
            for attachment, error in error_files:
                self.stdout.write(
                    f"ID={attachment.id}, 名称={attachment.name}, 错误={error}"
                )

        if not missing_files and not error_files:
            self.stdout.write(self.style.SUCCESS("所有附件文件存在且无错误!"))
