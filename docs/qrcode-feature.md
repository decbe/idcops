# 机柜 / 设备二维码功能

> 实现日期：2026-04-22  
> 涉及模型：`Rack`（机柜）、`Device`（设备）  
> 无数据库迁移，依赖新增：`qrcode[pil]>=8.0`

---

## 1. 功能概述

本功能为机柜和设备提供二维码生成、公开扫码查看、批量导出打印三大能力：

| 能力 | 说明 |
|------|------|
| 生成二维码 | 在详情页弹出 Modal 展示二维码图片，支持单张 PNG 下载 |
| 公开扫码页 | 扫码后无需登录即可查看指定字段（字段范围可配置） |
| 扫码识别页 | 独立相机扫码页，兼容域名变更，提取 token 后以当前域名跳转 |
| 批量导出 | 列表页多选后批量导出 ZIP（PNG 集合）或打印友好 HTML |

---

## 2. 核心设计：Token 机制

### 2.1 无数据库字段

Token 由 Django `signing.Signer` 对 `"{app_label}.{model_name}:{pk}"` 字符串签名生成，**不需要在数据库中新增任何字段**。

```
token = Signer(salt="dcrm-qr-public").sign("dcrm.rack:42")
# 示例输出：dcrm.rack:42:u_9l9jNACH1FbOb-BbL7cL8TH1R...
```

### 2.2 防伪造

底层使用 **HMAC-SHA256**，以 `SECRET_KEY + salt` 为密钥。没有服务端密钥无法伪造 token，篡改任意字符均触发 `BadSignature`，视图返回 404。

### 2.3 域名变更兼容

二维码图像中编码的是**完整 URL**（含域名），例如：

```
https://idc.example.com/scan/dcrm.rack:42:u_9l9jNACH1FbOb.../
```

域名变更后，运维人员访问**新域名下**的 `/scan/` 扫码识别页，用摄像头扫实体贴纸，前端 JS 从扫描结果中提取 token 路径段，直接以**当前域名相对路径**跳转 `/scan/{token}/`，旧域名部分被完全丢弃。

### 2.4 Token 失效情形

| 情形 | 结果 |
|------|------|
| `SECRET_KEY` 变更 | 所有历史 token 立即失效，需重新打印二维码 |
| 对象被删除（pk 不存在） | `get_object_for_this_type` 抛出 `DoesNotExist`，返回 404 |
| Token 被篡改 | `BadSignature`，返回 404 |

---

## 3. 新增文件清单

```
dcrm/
├── utilities/
│   └── qr.py                          # Token、图像生成、URL 构建工具
├── views/
│   └── qrcode.py                      # 4 个视图
├── actions/
│   └── qrcode.py                      # 2 个批量 Action
└── templates/
    └── scan/
        ├── public_detail.html         # 公开扫码详情页（无需登录）
        ├── scanner.html               # 摄像头扫码识别页
        └── print_qrcodes.html         # 批量打印 HTML 模板
```

---

## 4. 修改文件清单

| 文件 | 改动内容 |
|------|----------|
| `requirements.txt` | 新增 `qrcode[pil]>=8.0` |
| `idcops/settings.py` | 新增 `QR_PUBLIC_FIELDS` 配置项 |
| `dcrm/urls.py` | 注册 4 条新路由 |
| `dcrm/actions/__init__.py` | 导入 `qrcode` actions 模块 |
| `dcrm/views/mixins/detail.py` | `get_context_data()` 注入 `qr_token`、`qr_image_url`、`qr_download_url` |
| `dcrm/templates/detail.html` | box-tools 区域添加"二维码"按钮 + Bootstrap Modal |
| `dcrm/templates/rack/detail.html` | 同上（机柜详情专属模板单独处理） |

---

## 5. URL 路由

| URL | 视图 | 认证 | 说明 |
|-----|------|------|------|
| `/scan/` | `QRScannerPageView` | 无需登录 | 摄像头扫码识别页 |
| `/scan/<token>/` | `QRPublicDetailView` | 无需登录 | 公开详情页 |
| `/qr/image/<token>/` | `QRImageView` | 需要登录 | inline PNG，供 Modal 嵌入 |
| `/qr/download/<token>/` | `QRImageDownloadView` | 需要登录 | attachment PNG，单张下载 |

> `SITE_PREFIX` 环境变量会影响前缀，如配置了 `SITE_PREFIX=/app`，则路由变为 `/app/scan/` 等。

---

## 6. 配置项说明

### 6.1 `QR_PUBLIC_FIELDS`（`idcops/settings.py`）

控制未登录用户在公开扫码页面能看到哪些字段：

```python
QR_PUBLIC_FIELDS = {
    "dcrm.rack": ["name", "room", "status", "rack_type", "u_height", "tenant"],
    "dcrm.device": ["name", "model", "type", "rack", "position", "status"],
}
```

- 键格式：`"{app_label}.{model_name}"`（全小写）
- 值：字段名列表，支持 ForeignKey（显示其 `__str__`）和 ManyToMany（以逗号分隔）
- 若某模型未配置，公开页面显示空字段列表

### 6.2 `QR_SIGNER_SALT`（`dcrm/utilities/qr.py`）

默认值 `"dcrm-qr-public"`，固化在代码中。如需更换 salt（相当于批量作废所有已打印二维码），修改 `QR_SIGNER_SALT` 常量后重新部署即可。

---

## 7. 各模块详细说明

### 7.1 `dcrm/utilities/qr.py`

| 函数 | 签名 | 说明 |
|------|------|------|
| `generate_token` | `(obj) -> str` | 对任意模型实例生成防伪 token |
| `resolve_token` | `(token) -> Model` | token 还原为实例，签名错误/对象不存在均抛异常 |
| `generate_qr_image` | `(content: str) -> BytesIO` | 生成 PNG，纠错级别 L，box_size=8，border=4 |
| `get_public_url` | `(request, obj) -> str` | 拼接完整公开 URL，兼容 `SITE_PREFIX` |
| `get_public_fields_config` | `() -> dict` | 读取 `settings.QR_PUBLIC_FIELDS`，取不到则返回内置默认值 |

### 7.2 `dcrm/views/qrcode.py`

**`QRPublicDetailView`**（无认证）
- 解析 token → 获取对象 → 读取 `QR_PUBLIC_FIELDS` 配置 → 渲染 `scan/public_detail.html`
- 签名错误或对象不存在 → 404

**`QRScannerPageView`**（无认证）
- 纯模板视图，渲染 `scan/scanner.html`
- 页面使用 `html5-qrcode` 库（CDN）启动摄像头扫码

**`QRImageView`**（需登录）
- 动态生成 PNG，`Content-Disposition: inline`，供详情页 `<img>` 标签加载

**`QRImageDownloadView`**（需登录）
- 动态生成 PNG，`Content-Disposition: attachment`，文件名格式：`{model}_{pk}_{name}.png`

### 7.3 `dcrm/actions/qrcode.py`

**`export_qrcodes_zip`**（注册到 Rack、Device，需 `view` 权限）
- 遍历选中对象，逐一生成 PNG 写入 `zipfile.ZipFile`（DEFLATED 压缩）
- 文件名：`{model}_{pk}_{safe_name}.png`
- 响应：`application/zip`，文件名：`{model}_qrcodes.zip`

**`export_qrcodes_print`**（注册到 Rack、Device，需 `view` 权限）
- 遍历选中对象，PNG 转 base64 内嵌到 HTML
- 渲染 `scan/print_qrcodes.html`：A4 布局，3 列，含 `@media print` CSS
- 直接在浏览器中 `Ctrl+P` / `Cmd+P` 打印即可

### 7.4 模板说明

**`scan/public_detail.html`**
- 不继承 `base.html`，独立轻量布局，无侧栏
- 仅展示 `QR_PUBLIC_FIELDS` 配置的字段
- 底部提供"登录查看完整信息"和"扫码识别"两个入口按钮

**`scan/scanner.html`**
- 使用 `html5-qrcode@2.3.8`（CDN 引入）
- 扫描成功后：从结果中正则匹配 `/scan/{token}/`，提取 token，以相对路径跳转
- 若扫描结果不含路径模式，直接将整个字符串作为 token 尝试
- 兼容域名变更：旧 URL 中的 host 部分被完全丢弃

**`scan/print_qrcodes.html`**
- 每页 3 列，每个卡片含：QR 图像（140px）、模型类型、对象名称、原始 URL
- `@media print` 隐藏工具栏，`@page` 设置 A4 尺寸和页边距
- 图像 base64 内嵌，无需服务器回源，离线可用

---

## 8. 详情页 UI 说明

所有使用 `DetailViewMixin` 的详情页（包括通用 `detail.html` 和机柜专属 `rack/detail.html`）：

1. **"二维码"按钮**：位于右上角 box-tools 区域，图标 `fa fa-qrcode`
2. **Bootstrap Modal**：
   - 展示该对象的 QR 码图片（`/qr/image/<token>/`）
   - "下载 PNG"按钮（`/qr/download/<token>/`）
   - "公开页面"按钮（`/scan/<token>/`，新标签页打开）
   - "关闭"按钮

> `DetailViewMixin.get_context_data()` 自动注入 `qr_token`、`qr_image_url`、`qr_download_url`，若 token 生成失败（异常）则 `qr_token=None`，按钮不渲染。

---

## 9. 使用流程

### 9.1 单个机柜/设备生成二维码

1. 进入机柜或设备详情页
2. 点击右上角"二维码"按钮
3. Modal 展示二维码图片
4. 点击"下载 PNG"保存图片 → 打印张贴到机柜/设备上

### 9.2 批量导出二维码

1. 进入机柜或设备列表页
2. 勾选需要导出的记录（支持跨页多选）
3. 在操作栏选择"批量导出二维码 (ZIP)"→ 下载 ZIP，解压后打印
4. 或选择"批量打印二维码"→ 浏览器打开打印页，`Ctrl+P` 直接打印

### 9.3 扫码查看详情

**方式一（推荐）：直接扫码**
- 手机扫描贴纸上的二维码 → 直接打开公开详情页，无需登录

**方式二：扫码识别页（域名变更后使用）**
1. 在新域名下访问 `/scan/`
2. 允许摄像头权限
3. 对准实体贴纸扫码
4. 自动跳转到当前域名下的公开详情页

---

## 10. 安全说明

| 端点 | 认证要求 | 风险说明 |
|------|----------|----------|
| `/scan/<token>/` | 无需登录 | 仅展示 `QR_PUBLIC_FIELDS` 中配置的字段，默认不含敏感信息（IP、账号等） |
| `/scan/` | 无需登录 | 纯静态页面，无数据查询 |
| `/qr/image/<token>/` | 需要登录 | 防止外部批量爬取生成二维码图片 |
| `/qr/download/<token>/` | 需要登录 | 同上 |

**防伪造**：token 由 HMAC-SHA256 签名，外部无法伪造。枚举攻击不可行——即使猜到 `dcrm.rack:1`，也无法通过验签。

**信息泄露**：公开页面展示字段由 `QR_PUBLIC_FIELDS` 控制，运维人员应在部署前确认字段列表不包含租户合同金额、IP 地址、访问凭据等敏感字段。

---

## 11. 后续待办事项

### P0（功能完善）

- [ ] **`QR_PUBLIC_FIELDS` 管理界面**  
  当前只能通过修改 `settings.py` 调整公开字段。计划在"系统配置"页面（`/configuration/`）增加 UI，支持按模型动态配置公开字段，无需重启服务。

- [ ] **二维码缓存**  
  当前每次访问 `/qr/image/<token>/` 都实时生成 PNG。对于频繁访问的详情页，可将 PNG 缓存到 Redis（以 token 为 key），`SECRET_KEY` 变更时清空缓存。

- [ ] **公开页面访问日志**  
  记录扫码访问的 IP、UA、时间、对象信息，用于统计和安全审计。可复用现有 `LogEntry` 模型。

### P1（体验优化）

- [ ] **打印模板优化**  
  - 支持用户选择每行列数（2 列 / 3 列 / 4 列）
  - 支持自定义标签文字（如显示资产编号、机房位置）
  - 支持添加 Logo 水印

- [ ] **二维码尺寸可配置**  
  在 `settings.py` 或管理界面提供 `QR_BOX_SIZE`、`QR_ERROR_CORRECTION` 配置，满足不同打印精度需求。

- [ ] **列表页行内二维码入口**  
  在机柜/设备列表页每行操作列添加二维码图标，点击直接弹出 Modal（目前只有详情页有此入口）。

- [ ] **公开页面 Logo 和标题自定义**  
  `public_detail.html` 当前使用内联样式，计划读取系统配置的 `SITE_TITLE` 和 Logo 展示品牌信息。

### P2（扩展支持）

- [ ] **扩展至其他模型**  
  当前只支持 `Rack` 和 `Device`。可按需扩展到 `Room`（机房）、`Tenant`（租户）、`InventoryItem`（库存物品）等，仅需在 `QR_PUBLIC_FIELDS` 中添加对应配置。

- [ ] **二维码批量重新生成工具**  
  `SECRET_KEY` 变更后，提供 Management Command（`manage.py regenerate_qrcodes`）批量为所有机柜/设备重新生成 PNG 并打包，方便运维批量重印。

- [ ] **NFC 标签支持**  
  生成的 token URL 同样适用于 NFC 标签写入，`/scan/<token>/` 页面无需摄像头即可访问，架构上完全兼容，无需额外开发。

- [ ] **二维码与工单系统集成**  
  扫码后若设备处于故障状态，可在公开页面展示"报修"入口，跳转到工单系统（预留接口）。

- [ ] **批量导出 Excel（附二维码）**  
  在现有 ZIP 导出基础上，支持生成 Excel 表格，每行附带对应二维码图片，作为机柜/设备资产台账打印件。

### P3（运维工具）

- [ ] **二维码验证 CLI**  
  添加 Management Command：`manage.py verify_qr_token <token>`，用于运维快速在命令行验证 token 是否有效、指向哪个对象。

- [ ] **批量生成预生成文件（离线打印包）**  
  后台任务定期（如每月）为所有机柜/设备生成最新 PNG，存储到 `MEDIA_ROOT/qrcodes/` 目录，支持直接下载整个目录。

---

## 12. 本地开发验证步骤

```bash
# 1. 安装依赖
pip install 'qrcode[pil]'

# 2. 验证工具函数
SECRET_KEY=dev DJANGO_SETTINGS_MODULE=idcops.settings python manage.py shell -c "
from dcrm.utilities.qr import generate_qr_image, get_public_fields_config
print(get_public_fields_config())
buf = generate_qr_image('https://example.com/scan/test/')
print('PNG bytes:', len(buf.read()))
"

# 3. 验证 URL 路由
SECRET_KEY=dev DJANGO_SETTINGS_MODULE=idcops.settings python manage.py shell -c "
from django.urls import reverse
print(reverse('qr_scanner'))
print(reverse('qr_public_detail', args=['tok']))
print(reverse('qr_image', args=['tok']))
print(reverse('qr_download', args=['tok']))
"

# 4. 验证 Action 注册
SECRET_KEY=dev DJANGO_SETTINGS_MODULE=idcops.settings python manage.py shell -c "
from dcrm.actions import registry
print('Rack QR actions:', [a for a in registry._actions.get('dcrm.rack', {}) if 'qrcode' in a or 'print' in a])
print('Device QR actions:', [a for a in registry._actions.get('dcrm.device', {}) if 'qrcode' in a or 'print' in a])
"
```

---

## 13. 相关文件快速索引

```
dcrm/utilities/qr.py                   # Token 和图像生成核心
dcrm/views/qrcode.py                   # 视图层
dcrm/actions/qrcode.py                 # 批量 Action
dcrm/templates/scan/public_detail.html # 公开详情页
dcrm/templates/scan/scanner.html       # 扫码识别页
dcrm/templates/scan/print_qrcodes.html # 打印模板
idcops/settings.py                     # QR_PUBLIC_FIELDS 配置（约第 412 行）
dcrm/urls.py                           # 路由注册（约第 862 行）
dcrm/views/mixins/detail.py            # qr_token 上下文注入
dcrm/templates/detail.html             # 通用详情页二维码按钮+Modal
dcrm/templates/rack/detail.html        # 机柜详情页二维码按钮+Modal
```
