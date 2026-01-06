import json

from django.contrib.contenttypes.models import ContentType
from django.core import serializers

# from extras.utils import is_taggable

__all__ = (
    "deserialize_object",
    "serialize_object",
)


def serialize_object(
    obj, resolve_tags=True, extra=None, exclude=None, delete=False, repr=False
):
    """Return a generic JSON representation of an object using Django's built-in serializer. (This is used for things like
    change logging, not the REST API.) Optionally include a dictionary to supplement the object data. A list of keys
    can be provided to exclude them from the returned dictionary.

    Args:
        obj: The object to serialize
        resolve_tags: If true, any assigned tags will be represented by their names
        extra: Any additional data to include in the serialized output. Keys provided in this mapping will
            override object attributes.
        exclude: An iterable of attributes to exclude from the serialized output

    """
    json_str = serializers.serialize("json", [obj])
    data = json.loads(json_str)[0]["fields"]
    exclude = exclude or [
        "created_at",
        "updated_at",
        "deleted_at",
        "created_by",
        "updated_by",
        "password",
        "_password",
        "ssh_key",
        "data_center",
        "custom_fields",
        "custom_field_data",
        "extra_data",
        "metadata",
    ]
    if delete:
        exclude = exclude or ["password", "_password"]

    # Skip any excluded attributes
    for key in list(data.keys()):
        if key in exclude:
            data.pop(key)

    # 添加对象的 __str__ 值到序列化结果中
    if repr:
        data["repr"] = str(obj)

    # Append any extra data
    if extra is not None:
        data.update(extra)

    return data


def deserialize_object(model, fields, pk=None):
    """Instantiate an object from the given model and field data. Functions as
    the complement to serialize_object().
    """
    content_type = ContentType.objects.get_for_model(model)
    if "custom_fields" in fields:
        fields["custom_field_data"] = fields.pop("custom_fields")
    opts = model._meta
    fields = [field.name for field in opts.get_fields() if field.name in fields.keys()]
    data = {
        "model": ".".join(content_type.natural_key()),
        "pk": pk,
        "fields": fields,
    }
    instance = list(serializers.deserialize("python", [data]))[0]

    return instance
