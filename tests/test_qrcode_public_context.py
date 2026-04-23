from types import SimpleNamespace

import pytest
from django.conf import settings
from django.template.loader import render_to_string

from dcrm.views import qrcode
from dcrm.utilities.qr import get_public_fields_config


class FakeRelatedManager:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class FakeLookup:
    def __init__(self, model, fields, custom_fields=None, primary_link=False):
        self.model = model
        self.fields = fields
        self.custom_fields = custom_fields
        self.primary_link = primary_link

    def get_field_label(self, field_name):
        labels = {
            "status": "状态",
            "asset_tag": "资产标签",
        }
        if field_name not in labels:
            raise LookupError(field_name)
        return labels[field_name]

    def get_field_value(self, obj, field_name):
        values = {
            "status": '<a href="/device-status/"><span class="label bg-green">运行中</span></a>',
            "asset_tag": "ASSET-001",
        }
        if field_name not in values:
            raise LookupError(field_name)
        return values[field_name]


def _build_fake_object():
    return SimpleNamespace(
        _meta=SimpleNamespace(
            app_label="dcrm",
            model_name="device",
            verbose_name="设备",
        ),
        tags=FakeRelatedManager(["blue", "prod"]),
    )


def test_sanitize_public_value_strips_link_but_keeps_inner_markup():
    value = '<a href="/rack/1/"><span class="label bg-blue">R1</span></a>'

    rendered = qrcode._sanitize_public_value(value)

    assert str(rendered) == '<span class="label bg-blue">R1</span>'


def test_get_public_context_uses_lookup_display_and_fallback(monkeypatch):
    obj = _build_fake_object()

    monkeypatch.setattr(qrcode, "resolve_token", lambda token: obj)
    monkeypatch.setattr(
        qrcode,
        "get_public_fields_config",
        lambda: {"dcrm.device": ["status", "asset_tag", "tags"]},
    )
    monkeypatch.setattr(qrcode, "_get_public_custom_fields", lambda current: ["cf"])
    monkeypatch.setattr(qrcode, "LookupFields", FakeLookup)
    monkeypatch.setattr(
        qrcode,
        "get_object_display",
        lambda current: ("name", "设备-A", "/device/1/"),
    )

    context = qrcode._get_public_context("token-1")

    assert context["object"] is obj
    assert context["object_name"] == "设备-A"
    assert context["model_verbose_name"] == "设备"
    assert context["fields"] == [
        {"label": "状态", "value": '<span class="label bg-green">运行中</span>'},
        {"label": "资产标签", "value": "ASSET-001"},
        {"label": "tags", "value": "blue, prod"},
    ]


def test_public_detail_template_renders_rich_value_markup():
    html = render_to_string(
        "scan/public_detail.html",
        {
            "model_verbose_name": "设备",
            "object_name": "设备-A",
            "fields": [
                {
                    "label": "状态",
                    "value": '<span class="label bg-green">运行中</span>',
                }
            ],
            "request": SimpleNamespace(path="/scan/token/"),
        },
    )

    assert '<span class="label bg-green">运行中</span>' in html


def test_qr_public_fields_include_onlinedevice_config():
    config = get_public_fields_config()

    assert config["dcrm.onlinedevice"] == [
        "name",
        "model",
        "type",
        "rack",
        "position",
        "status",
    ]
    assert settings.QR_PUBLIC_FIELDS["dcrm.onlinedevice"] == config["dcrm.onlinedevice"]


def test_qr_public_fields_include_requested_rack_config():
    config = get_public_fields_config()

    assert config["dcrm.rack"] == [
        "room",
        "name",
        "rack_type",
        "status",
        "space_usage",
        "tenant",
        "opening_date",
        "contract_power",
        "u_height",
        "pdu_count",
        "pdu_16a_count",
        "description",
    ]
    assert settings.QR_PUBLIC_FIELDS["dcrm.rack"] == config["dcrm.rack"]
