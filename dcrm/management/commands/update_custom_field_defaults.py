from django.core.management.base import BaseCommand

from dcrm.models import CustomField


class Command(BaseCommand):
    help = "将自定义字段的默认值更新到所有关联的对象中"

    def add_arguments(self, parser):
        parser.add_argument("--field-id", type=int, help="指定要更新的自定义字段ID")

    def handle(self, *args, **options):
        field_id = options.get("field_id")

        if field_id:
            # 更新指定字段
            try:
                field = CustomField.objects.get(id=field_id)
                self.stdout.write(f"Updating objects for custom field: {field.name}")
                field.update_related_objects()
            except CustomField.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"Custom field with ID {field_id} not found")
                )
        else:
            # 更新所有字段
            for field in CustomField.objects.all():
                if field.default is not None:
                    self.stdout.write(
                        f"Updating objects for custom field: {field.name}"
                    )
                    field.update_related_objects()

        self.stdout.write(
            self.style.SUCCESS("Successfully updated custom field values")
        )
