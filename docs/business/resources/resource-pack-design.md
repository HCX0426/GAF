---
summary: GAF 资源包规范设计 (合并 v1.0 spec + v1.1 guide)
applies_to: ['backend', 'design']
status: deprecated
superseded_by: docs/business/tasks/pipeline-design.md
key_decisions:
  - 资源包目录结构 (含 skills/ + custom_tasks/)
  - manifest.json JSON Schema 定义
  - config/tasks/monitors 文件格式规范
  - 导入/导出流程 (含 Python 代码)
  - 版本兼容性规则 + 兼容矩阵
  - 资源包与数据库映射
  - 资源包安全 (沙箱执行)
last_updated: 2026-07-22
---

> ⚠️ **Task 4.34 (P2-19, 2026-07-28)**: 本文档 §5.2 的 chain schema 已废弃,
> 新资源包应使用 pipeline schema (nodes + node_type)。
> 详见 docs/business/tasks/pipeline-design.md 或 docs/business/tasks/execution-reality.md。

# GAF 资源包规范设计

> 版本：1.3 (合并 v1.0 spec + v1.1 guide) | 日期：2026-07-22 | spec-37 文档治理合并
>
> **历史**: v1.0 (2026-05-17, SubTask 1.11, spec) + v1.1 (2026-05-18, 阶段七, guide) → v1.2 (2026-07-19, spec-37 合并) → v1.3 (2026-07-22, 对齐代码实现)

## 1. 概述

资源包（Resource Pack）是 GAF 中组织任务定义、模板图片、配置文件和监控规则的基本单元。本规范定义资源包的目录结构、必需文件、JSON Schema、导入导出流程和版本兼容性规则。

---

## 2. 目录结构规范

### 2.1 标准目录结构

```
resource_pack/
├── manifest.json          # 元数据（名称、版本、目标应用、作者、GAF版本兼容性）
├── icon.png               # 资源包图标（可选，推荐 256x256）
├── README.md              # 资源包说明（可选）
├── config/                # 配置文件目录
│   ├── settings.json      # 全局设置（基准分辨率、OCR引擎、截图方法偏好等）
│   ├── rois.json          # ROI 区域定义
│   ├── thresholds.json    # 匹配阈值配置
│   └── delays.json        # 延迟配置
├── templates/             # 模板图片（按功能分子目录）
│   ├── login/             # 登录相关模板
│   ├── public/            # 公共UI模板（主界面、返回键、跳过等）
│   ├── common/            # 通用模板（confirm/cancel/close 按钮）
│   ├── main_ui/           # 主界面模板
│   ├── get_pvp/           # PVP竞技场模板
│   ├── sweep_daily/       # 每日扫荡模板
│   ├── map_collection/    # 地图收集模板
│   ├── intensive_decomposition/  # 装备分解/精炼模板
│   ├── get_restaurant/    # 餐厅任务模板
│   ├── get_guild/         # 公会任务模板
│   ├── get_email/         # 邮件领取模板
│   ├── pass_activity/     # 通行证活动模板
│   ├── pass_rewards/      # 通行证奖励模板
│   └── lucky_draw/        # 抽奖模板
├── tasks/                 # 任务定义
│   ├── daily_sign_in.yaml # 状态机任务
│   ├── stage_battle.json  # Pipeline 任务
│   └── custom/            # 自定义任务目录
│       └── auto_battle.json
├── monitors/              # 监控规则
│   ├── popup_handler.yaml # 弹窗处理器
│   ├── story_skip.yaml    # 剧情跳过器
│   └── error_recovery.yaml # 错误恢复规则
├── custom_tasks/          # 自定义任务模板
│   └── template.json      # 自定义任务模板文件
└── skills/                # Skill 定义目录（可选，设计预留，代码未实现）
    └── analyze_error.yaml # 自定义 Skill
```

> **注**: `skills/` 目录为设计预留项。当前 `backend/resources/validators.py:13` 的 `OPTIONAL_DIRS = ["config", "monitors", "tasks", "custom_tasks"]` 不含 `skills/`，且 `backend/resources/import_utils.py` 也未提供 `import_skills` 函数。导入流程不会扫描或注册 `skills/` 下的内容。

### 2.2 目录说明

| 目录 | 必需 | 说明 |
|------|------|------|
| `config/` | 否 | 全局配置文件，包含设置和 ROI 定义 |
| `templates/` | 是 | 模板图片目录，按功能分子目录组织 |
| `tasks/` | 否 | 任务定义文件，支持 YAML（状态机）和 JSON（Pipeline）格式 |
| `monitors/` | 否 | 监控规则定义，YAML 格式 |
| `custom_tasks/` | 否 | 自定义任务模板，JSON 格式 |
| `skills/` | 否 | Skill 定义，YAML 格式（设计预留，代码未实现） |

### 2.3 目录命名规范

| 规则 | 说明 |
|------|------|
| 目录名使用小写字母 + 下划线 | `daily_farm/` 而非 `DailyFarm/` |
| 模板图片按界面/功能分组 | `templates/login/`、`templates/battle/` |
| 任务定义与模板图片对应 | `tasks/daily_sign_in.yaml` ↔ `templates/login/` |
| 配置文件使用 JSON 格式 | `config/settings.json`、`config/rois.json` |
| 监控规则使用 YAML 格式 | `monitors/popup_handler.yaml` |

---

## 3. manifest.json 规范

### 3.1 必需字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 资源包名称，唯一标识 |
| `version` | string | 语义化版本号 (SemVer) |
| `target_app` | string | 目标应用标识 |
| `author` | string | 作者 |
| `gaf_version` | string | 兼容的 GAF 最低版本 |

> **字段映射**: manifest 中的 `gaf_version` 在导入时映射到数据库模型 `ResourcePack.gaf_version_compat` 字段，而非 `gaf_version`。参见 `backend/resources/models.py:34`（字段定义）和 `backend/resources/import_utils.py:145`（`"gaf_version_compat": manifest.get("gaf_version", "")`）。校验逻辑在 `backend/resources/validators.py:15` 的 `MANIFEST_REQUIRED_FIELDS = ["name", "version", "target_app", "author", "gaf_version"]` 中按 manifest 字段名 `gaf_version` 进行校验。

### 3.2 可选字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `description` | string | 资源包描述 |
| `icon` | string | 图标文件相对路径 |
| `tags` | array | 标签列表 |
| `dependencies` | array | 依赖的其他资源包 |

### 3.3 JSON Schema 定义

```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "GAF Resource Pack Manifest",
    "type": "object",
    "required": ["name", "version", "target_app", "author", "gaf_version"],
    "properties": {
        "name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 255,
            "pattern": "^[a-zA-Z0-9_\\-\\u4e00-\\u9fa5]+$",
            "description": "资源包名称，唯一标识"
        },
        "version": {
            "type": "string",
            "pattern": "^\\d+\\.\\d+\\.\\d+$",
            "description": "语义化版本号 (SemVer)"
        },
        "gaf_version": {
            "type": "string",
            "pattern": "^>=\\d+\\.\\d+\\.\\d+$",
            "description": "兼容的 GAF 最低版本"
        },
        "author": {"type": "string", "description": "作者"},
        "description": {"type": "string", "maxLength": 2000, "description": "资源包描述"},
        "target_app": {"type": "string", "description": "目标应用包名或标识"},
        "icon": {"type": "string", "description": "图标文件相对路径"},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "标签"},
        "dependencies": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "version"],
                "properties": {
                    "name": {"type": "string"},
                    "version": {"type": "string"}
                }
            },
            "description": "依赖的其他资源包"
        },
        "files": {
            "type": "object",
            "required": ["tasks", "templates"],
            "properties": {
                "tasks": {"type": "array", "items": {"type": "string"}, "description": "任务定义文件列表"},
                "templates": {"type": "array", "items": {"type": "string"}, "description": "模板图片文件列表"},
                "config": {"type": "array", "items": {"type": "string"}, "description": "配置文件列表"},
                "monitors": {"type": "array", "items": {"type": "string"}, "description": "监控规则文件列表"},
                "skills": {"type": "array", "items": {"type": "string"}, "description": "Skill 定义文件列表"}
            }
        }
    }
}
```

### 3.4 示例

```json
{
  "name": "BD2-AUTO Default",
  "version": "1.0.0",
  "target_app": "com.nexon.bluearchive",
  "author": "GAF",
  "gaf_version": ">=1.0.0",
  "description": "蔚蓝档案默认资源包",
  "icon": "icon.png",
  "tags": ["蔚蓝档案", "日常", "刷图"],
  "dependencies": [],
  "files": {
    "tasks": ["tasks/daily_farm.json", "tasks/login_flow.yaml"],
    "templates": ["templates/main_ui/start_button.png", "templates/login/login_screen.png"],
    "config": ["config/rois.json", "config/thresholds.json"],
    "monitors": ["monitors/popup_handler.yaml"],
    "skills": []
  }
}
```

---

## 4. config/ 配置文件规范

### 4.1 settings.json

全局运行设置，定义截图、OCR、输入等偏好。

```json
{
  "base_resolution": [1280, 720],
  "ocr_engine": "rapidocr",
  "screenshot_method_preference": "auto",
  "input_method_preference": "auto",
  "screenshot_cache_ttl": 50,
  "humanize_enabled": true,
  "humanize_offset": 5
}
```

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `base_resolution` | array | [1280, 720] | 基准分辨率 [宽, 高] |
| `ocr_engine` | string | "rapidocr" | OCR 引擎选择 |
| `screenshot_method_preference` | string | "auto" | 截图方法偏好 |
| `input_method_preference` | string | "auto" | 输入方法偏好 |
| `screenshot_cache_ttl` | int | 50 | 截图缓存 TTL（毫秒） |
| `humanize_enabled` | bool | true | 是否启用拟人化操作 |
| `humanize_offset` | int | 5 | 拟人化偏移像素 |

### 4.2 rois.json

ROI（Region of Interest）区域定义，用于模板匹配和操作定位。

```json
{
  "full_screen": [0, 0, 1280, 720],
  "top_bar": [0, 0, 1280, 80],
  "bottom_bar": [0, 640, 1280, 80],
  "center": [320, 180, 960, 540]
}
```

ROI 格式为 `[x, y, width, height]`。

### 4.3 thresholds.json (可选)

```json
{
  "default": 0.85,
  "login_screen": 0.9,
  "confirm_button": 0.95
}
```

### 4.4 delays.json (可选)

```json
{
  "after_click": 0.5,
  "after_screenshot": 0.1,
  "between_steps": 1.0
}
```

---

## 5. tasks/ 任务定义规范

### 5.1 状态机任务（YAML）

状态机任务使用 YAML 格式定义，包含状态、转换和动作。

```yaml
name: "每日签到任务"
description: "游戏每日签到状态机示例"
version: "1.0.0"
target_app: "example_game"
resource_pack: "default"

initial_state: "main_menu"

states:
  main_menu:
    description: "主界面"
    detect:
      template: "templates/main_menu_logo.png"
      roi: { x: 0, y: 0, w: 200, h: 100 }
      threshold: 0.85
    action:
      type: "click"
      target: "templates/sign_in_button.png"
    timeout: 30
    retry: 3
    transitions:
      - target: "sign_in_page"
        condition:
          template: "templates/sign_in_title.png"
          threshold: 0.8
```

### 5.2 Pipeline 任务（JSON）

Pipeline 任务按节点顺序执行，无 `edges` 字段时按 `nodes` 列表顺序自动链接（线性模式，等价于原 chain 顺序执行）；支持节点内控制流字段（`pre_verify` / `post_verify` / `retry` / `fallback` / `continue_on_error`）。

```json
{
  "name": "stage_battle",
  "execution_mode": "pipeline",
  "task_definition": {
    "nodes": [
      {
        "id": "step_1",
        "node_type": "template_match",
        "config": {"template_id": "tpl_login_btn", "threshold": 0.8}
      }
    ]
  }
}
```

---

## 6. monitors/ 监控规则规范

监控规则使用 YAML 格式，定义自动响应的屏幕事件。

```yaml
name: popup_handler
description: 通用弹窗处理器
rules:
  - template: common/close_button
    action: click
    description: 关闭弹窗
  - template: common/confirm_button
    action: click
    description: 确认弹窗
  - template: common/cancel_button
    action: click
    description: 取消弹窗
```

---

## 7. custom_tasks/ 自定义任务模板规范

自定义任务模板使用 JSON 格式，提供用户创建自定义任务的基础结构。

> **schema 说明**: chain schema 已废弃 (spec-2026-07-27-execution-path-unification)，
> 模板已迁移到 pipeline schema (`mode: "pipeline"` + `nodes: [{node_type, config, retry, fallback, ...}]`)。

```json
{
  "name": "自定义任务模板",
  "description": "用于创建自定义任务的模板",
  "mode": "pipeline",
  "nodes": [
    {
      "id": "step_1",
      "name": "步骤1",
      "node_type": "template_match",
      "config": {
        "template_id": "",
        "roi": "full_screen"
      },
      "retry": {
        "max_retries": 3,
        "base_delay": 1000
      },
      "fallback": {
        "action": "skip"
      }
    }
  ]
}
```

---

## 8. 资源包校验规则

### 8.1 必需项校验

- `manifest.json` 必须存在且包含所有必需字段
- `templates/` 目录必须存在

### 8.2 结构校验

- 校验所有必需目录是否存在
- 校验 manifest.json 字段完整性（按 §3.3 JSON Schema）
- 校验配置文件格式正确性

### 8.3 版本兼容性校验

- 检查 `gaf_version` 与当前 GAF 版本兼容性（详见 §10）
- 主版本号不同视为不兼容

---

## 9. 导入/导出流程

### 9.1 导出流程

1. 选择资源包
2. 收集所有文件
3. 验证 manifest.json 完整性
4. 校验所有文件是否存在
5. 打包为 ZIP 文件（`.gafpack` 格式）
   - 文件名格式: `{name}-{version}.gafpack`
   - 保留目录结构
   - 计算文件校验和
6. 生成导出报告

```python
import json
import zipfile
import hashlib
from pathlib import Path

def export_resource_pack(pack_dir: str, output_dir: str) -> str:
    """导出资源包为 .gafpack 文件"""
    pack_path = Path(pack_dir)
    manifest_path = pack_path / "manifest.json"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    pack_name = manifest["name"]
    pack_version = manifest["version"]
    output_file = Path(output_dir) / f"{pack_name}-{pack_version}.gafpack"

    checksums = {}
    with zipfile.ZipFile(output_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in pack_path.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(pack_path)
                zf.write(file_path, rel_path)
                with open(file_path, "rb") as f:
                    checksums[str(rel_path)] = hashlib.sha256(f.read()).hexdigest()

        checksum_manifest = json.dumps(checksums, indent=2, ensure_ascii=False)
        zf.writestr(".checksums.json", checksum_manifest)

    return str(output_file)
```

### 9.2 导入流程

1. 上传资源包（ZIP 文件或目录路径）
2. 解压到临时目录（ZIP 模式）
3. 验证 manifest.json
   - 格式校验 (JSON Schema)
   - 版本兼容性检查
   - 依赖检查
4. 校验文件完整性 (checksums)——（未实现：导入仅读 manifest/结构，checksums 仅在导出时生成）
5. 检查文件名冲突
6. 复制到资源包目录
7. 注册到数据库 (ResourcePack 模型)
8. 清理临时目录
9. 返回导入结果

```python
def import_resource_pack(pack_file: str, target_dir: str) -> dict:
    """导入 .gafpack 资源包"""
    temp_dir = Path(target_dir) / ".temp_import"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(pack_file, "r") as zf:
            zf.extractall(temp_dir)

        manifest_path = temp_dir / "manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        validate_manifest(manifest)

        checksums_path = temp_dir / ".checksums.json"
        if checksums_path.exists():
            with open(checksums_path, "r", encoding="utf-8") as f:
                checksums = json.load(f)
            verify_checksums(temp_dir, checksums)

        pack_name = manifest["name"]
        pack_version = manifest["version"]
        dest_dir = Path(target_dir) / f"{pack_name}_{pack_version}"

        if dest_dir.exists():
            raise ResourcePackConflictError(f"Resource pack already exists: {dest_dir}")

        import shutil
        shutil.move(str(temp_dir), str(dest_dir))

        return {
            "name": pack_name,
            "version": pack_version,
            "directory": str(dest_dir),
            "status": "imported",
        }
    finally:
        if temp_dir.exists():
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
```

---

## 10. 版本兼容性规则

### 10.1 版本号规则

采用语义化版本（SemVer）：`MAJOR.MINOR.PATCH`

| 版本位 | 变更含义 | 兼容性 |
|--------|---------|--------|
| MAJOR | 不兼容的 API 变更 | 需要升级 GAF |
| MINOR | 向后兼容的功能新增 | 兼容同 MAJOR 版本 |
| PATCH | 向后兼容的问题修复 | 完全兼容 |

### 10.2 兼容性检查

```python
from packaging.version import Version

def check_compatibility(pack_gaf_version: str, current_gaf_version: str) -> bool:
    """检查资源包与当前 GAF 版本的兼容性"""
    required = Version(pack_gaf_version.lstrip(">="))
    current = Version(current_gaf_version)

    if current.major == 0:
        return current >= required

    return current.major == required.major and current.minor >= required.minor
```

### 10.3 版本兼容矩阵

> **注**: 当前 GAF 应用版本为 `2.0.0`（参见 `backend/config/app_info.py:6` `APP_VERSION = '2.0.0'`）。下表按 2.0.x 主版本列出兼容矩阵。`backend/resources/validators.py:18` 中的内部常量 `GAF_VERSION = "0.1.0"` 为历史遗留，与实际应用版本不一致，待后续清理，本次不修改。

| 资源包 gaf_version | GAF 2.0.x |
|-------------------|-----------|
| >=0.1.0 | ✅ |
| >=0.2.0 | ✅ |
| >=1.0.0 | ✅ |
| >=2.0.0 | ✅ |
| >=3.0.0 | ❌ |

### 10.4 破坏性变更处理

当 GAF 升级引入破坏性变更时：

1. **迁移脚本**：提供资源包格式迁移脚本
2. **兼容层**：旧格式资源包在加载时自动转换
3. **警告提示**：不兼容的资源包在 UI 中显示警告
4. **版本锁定**：用户可选择锁定 GAF 版本以保持兼容

---

## 11. 示例资源包

### 11.1 最小资源包

```
minimal_pack/
├── manifest.json
└── tasks/
    └── hello.json
```

```json
// manifest.json
{
    "name": "minimal_pack",
    "version": "0.1.0",
    "gaf_version": ">=0.1.0",
    "author": "Demo",
    "description": "最小示例资源包",
    "files": {
        "tasks": ["tasks/hello.json"],
        "templates": []
    }
}
```

```json
// tasks/hello.json
{
    "name": "hello_world",
    "execution_mode": "pipeline",
    "task_definition": {
        "nodes": [
            {
                "id": "screenshot",
                "node_type": "screenshot",
                "config": {},
                "delay_after": 1.0
            }
        ]
    }
}
```

### 11.2 完整资源包

参见第 2 节目录结构和第 3.4 节 manifest.json 示例。完整资源包包含任务定义、模板图片、配置文件、监控规则等全部内容。

---

## 12. 资源包与数据库的映射

| 资源包文件 | 数据库模型 | 说明 |
|-----------|-----------|------|
| `manifest.json` | `ResourcePack` | 元数据映射到模型字段（`gaf_version` → `gaf_version_compat`，见 §3.1） |
| `tasks/*.json` | `Task.task_definition` | 任务定义存入 JSON 字段 |
| `tasks/*.yaml` | `Task.task_definition` | YAML 解析后存入 JSON 字段 |
| `tasks/custom/*.json` | `CustomTask.task_definition` | ❌ 代码未实现：`import_pipelines` 不扫 `tasks/custom/`，无 CustomTask 导入逻辑 |
| `config/settings.json` | `ResourcePack.config_data` | 全局设置存入 `config_data` JSON 字段（见 `import_utils.py:390-421` 的 `import_config`） |
| `config/rois.json` | 未映射 | **代码未实现**：`import_config` 仅处理 `settings.json`，不读取 `rois.json`。ROI 仅在 `validators.py` 中做格式校验，不写入数据库 |
| `config/thresholds.json` | 未映射 | **代码未实现**：导入流程不处理 |
| `config/delays.json` | 未映射 | **代码未实现**：导入流程不处理 |
| `monitors/*.yaml` | `MonitorRule.rule_definition` | 监控规则定义 |
| `skills/*.yaml` | 未映射 | **代码未实现**：无 `import_skills` 函数，设计预留 |
| `templates/**/*.png` | 文件系统 | 模板图片保留在文件系统 |

---

## 13. 资源包安全

### 13.1 安全检查

| 检查项 | 说明 |
|--------|--------|
| 文件类型 | 仅允许 .json/.yaml/.png/.jpg/.md 文件 |
| 文件大小 | 单文件不超过 10MB，总包不超过 500MB（设计规范，代码未实现：当前 `validators.py` 未校验文件大小） |
| 路径穿越 | 禁止 `../` 等路径穿越字符 |
| 脚本注入 | 任务定义中禁止包含可执行代码 |
| 校验和 | 导入时验证文件完整性 |

### 13.2 沙箱执行

自定义任务中的操作指令在受限环境中执行：

- 仅允许预定义的 action 类型
- 禁止文件系统写操作（除日志目录）
- 禁止网络请求（除 Server API）
- 禁止进程创建

---

## 14. 反模式 (历史教训)

- **N142 复制重命名必须改全部标识符** — 资源包文件复制时, 所有内部标识符 (name/path/template 引用) 必须同步更新
- **N145 WebSocket consumer 上行消息** — 资源包导入后必通过 consumer 通知前端刷新, 不能只 ACK
- **N150 pre-commit 失败根因修复** — 资源包相关 hook 失败时根因修复, 不用 `--no-verify` 绕过
