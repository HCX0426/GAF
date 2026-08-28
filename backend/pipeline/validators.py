"""
Pipeline 结构校验器
执行前端+后端联合检查：必填字段、孤立节点、模板引用、Pipeline 引用等
"""
from dataclasses import dataclass

from pipeline.models import Pipeline


@dataclass
class CheckItem:
    """单条校验结果。"""
    check: str
    status: str
    message: str
    node_id: str | None = None
    suggestion: str = ''


def _dict_to_check(item: CheckItem) -> dict:
    return {
        'check': item.check,
        'status': item.status,
        'message': item.message,
        'node_id': item.node_id,
        'suggestion': item.suggestion,
    }


def _node_type(node: dict) -> str | None:
    """兼容读取节点类型: 优先 node_type (canvas), 其次 type (legacy)."""
    return node.get('node_type') or node.get('type')


def _node_config(node: dict) -> dict:
    """兼容读取节点配置: 优先 data (canvas), 其次 config (nested)."""
    return node.get('data') or node.get('config') or {}


class PipelineValidator:
    """Pipeline 结构校验器。"""

    def validate(self, graph_data: dict, strict: bool = False) -> list[dict]:
        """执行所有校验，返回 CheckItem 字典列表。

        Args:
            graph_data: {"nodes": [...], "edges": [...]}
            strict: Task 4.26 (P0-6) — strict mode 拒绝任何旧 schema 字段
                (templateId/action/type/next_step/retry_interval/fallback_action 等),
                用于主动验证 schema 完全归一化。默认 False (宽松模式, 兼容历史)。
        """
        nodes = graph_data.get('nodes', [])
        edges = graph_data.get('edges', [])

        results: list[CheckItem] = []
        results.extend(self._check_required_fields(nodes))
        results.extend(self._check_template_refs(nodes))
        results.extend(self._check_pipeline_refs(nodes))
        results.extend(self._check_connectivity(nodes, edges))
        results.extend(self._check_entry_exit(nodes))
        if strict:
            results.extend(self._check_legacy_fields(nodes))

        return [_dict_to_check(item) for item in results]

    def _check_required_fields(self, nodes: list) -> list[CheckItem]:
        """检查每个节点类型的必填字段是否已填写。

        Task 4.27 (P0-7): 字段名归一化为 snake_case, 与前端 NodePropertyPanel
        和 Python dataclass 习惯一致。兼容历史 camelCase 字段 (validator 同时
        读取两种命名, 任一非 None 即视为 filled)。

        Task 4.66 (P0-15, 2026-07-28): 三元组 (canonical, legacy, optional)
        - optional=True 表示该字段缺失不报 fail (agent 有内置默认值)
        - OCR engine/language 改为可选 (agent 内部使用 RapidOCR 默认引擎+ch 语言)
        - wait timeout 兼容 legacy max_wait (agent WaitNode._get_timeout 已处理)
        - branch condition 兼容 legacy condition_variable 三件套
          (agent BranchNode._get_condition 已处理结构化 condition 对象)
        """
        results = []
        # Task 4.66: 三元组 (canonical, legacy, optional)
        # - legacy 可以是单字段名 (camelCase 别名) 或 tuple (多字段别名, 任一非 None 即视为 filled)
        node_required = {
            'click': [('x', None, False), ('y', None, False)],
            'direct_hit': [('x', None, False), ('y', None, False)],
            # Task 4.66: swipe 兼容 BD2 start/end 数组格式 — agent SwipeNode._get_coords 支持
            'swipe': [('x1', ('start', 'end'), False), ('y1', ('start', 'end'), False),
                      ('x2', ('start', 'end'), False), ('y2', ('start', 'end'), False)],
            'key_press': [('key', None, False)],
            'text_input': [('text', None, False)],
            # Task 4.66: template_match 兼容 agent legacy `template` 字段 (无 Id 后缀)
            'template_match': [('template_id', ('templateId', 'template'), False), ('threshold', None, False)],
            'template_match_any': [('templates', None, False), ('threshold', None, False)],
            # Task 4.66: OCR engine/language 改为可选 — agent 默认 RapidOCR + ch
            'ocr': [('engine', None, True), ('language', None, True)],
            'color_detect': [('target_color', None, False), ('tolerance', None, False)],
            'feature_match': [('template_id', None, False), ('min_match_count', None, False)],
            # Task 4.66: wait timeout 兼容 legacy max_wait
            # Note: 当 mode=fixed 时, agent 用 seconds 字段, timeout 不是必填
            # 下面 _check_required_fields_wait 会做 mode-aware 校验
            'wait': [('timeout', 'max_wait', False)],
            # Task 4.66: branch condition 兼容 legacy condition_variable 三件套
            'branch': [('condition', ('condition_variable', 'condition_operator', 'condition_value'), False)],
            'loop': [('count', 'maxIterations', False)],
            'random_delay': [('min_ms', 'minDelay', False), ('max_ms', 'maxDelay', False)],
            'notify': [('channel', 'channels', False)],
            'device_control': [('action', None, False)],
            'monitor': [('rule_id', 'ruleId', False)],
            'sub_pipeline': [('pipeline_id', 'pipelineId', False)],
            'goto': [('target', 'targetLabel', False)],
            'swipe_until': [('templates', None, False), ('x1', None, False), ('y1', None, False), ('x2', None, False), ('y2', None, False)],
            'login_account': [('account_id', 'accountId', False)],
            'switch_account': [('next_account_id', 'nextAccountId', False)],
            'switch_resource': [('resource_pack_id', 'resourcePackId', False)],
            'captcha_detect': [('targets', None, False)],
        }

        for node in nodes:
            node_type = _node_type(node)
            required = node_required.get(node_type, [])
            data = _node_config(node)
            missing = []

            # Task 4.66: wait 节点 mode-aware 校验
            # - mode=fixed: 仅需 seconds (timeout 可选)
            # - 其他 mode: 需 timeout 或 max_wait
            if node_type == 'wait':
                mode = (data.get('mode') or 'fixed').lower()
                if mode == 'fixed':
                    # fixed 模式只需 seconds
                    if data.get('seconds') is None:
                        missing.append('seconds')
                    # timeout/max_wait 可选, 不参与 missing
                else:
                    # 非 fixed 模式需 timeout 或 max_wait
                    if data.get('timeout') is None and data.get('max_wait') is None:
                        missing.append('timeout')
            else:
                for canonical, legacy, optional in required:
                    if optional:
                        # 可选字段: 不参与 missing 计数
                        continue
                    # Task 4.27: 优先 canonical
                    if data.get(canonical) is not None:
                        continue
                    # Task 4.66: legacy 可以是单字符串或 tuple (多字段任一非 None 即视为 filled)
                    if legacy:
                        if isinstance(legacy, tuple):
                            # 多字段别名: 任一非 None 即视为 filled (如 branch 的 legacy 三件套, swipe 的 start/end)
                            if any(data.get(item) is not None for item in legacy):
                                continue
                        elif data.get(legacy) is not None:
                            continue
                    missing.append(canonical)
            if missing:
                results.append(CheckItem(
                    check='required_fields',
                    status='fail',
                    message=f"节点 '{node.get('id')}' ({node_type}) 缺少必填字段: {', '.join(missing)}",
                    node_id=node.get('id'),
                    suggestion='请在属性面板中填写对应字段',
                ))
            else:
                results.append(CheckItem(
                    check='required_fields',
                    status='pass',
                    message=f"节点 '{node.get('id')}' 必填字段完整",
                    node_id=node.get('id'),
                ))
        return results

    def _check_legacy_fields(self, nodes: list) -> list[CheckItem]:
        """Task 4.26 (P0-6): strict mode 专用 — 扫描旧 schema 字段名, 拒绝新旧共存。

        触发条件: validate_payload?strict=true 时调用。
        检查 nodes[].config 中是否含 templateId/action(节点级)/type(节点级)/
        next_step/retry_interval/fallback_action 等旧字段, 有则返回 fail CheckItem,
        suggestion 提示归一化为 canonical 字段名。

        Task 4.66 (P0-15, 2026-07-28): 扩展 legacy 字段清单
        - 新增 max_wait (wait 节点) → canonical timeout
        - 新增 condition_variable / condition_operator / condition_value (branch 节点) → canonical condition
        - 新增 true_node_id / false_node_id (branch 节点) → canonical true_branch / false_branch
        - 新增 next_node_id (节点顶层) → canonical edges
        """
        results: list[CheckItem] = []
        # 旧 schema 字段 → canonical 字段名映射
        legacy_field_map = {
            'templateId': 'template_id',
            'hueMin': 'target_color',
            'hueMax': 'tolerance',
            'algorithm': 'template_id',
            'maxIterations': 'count',
            'minDelay': 'min_ms',
            'maxDelay': 'max_ms',
            'channels': 'channel',
            'ruleId': 'rule_id',
            'pipelineId': 'pipeline_id',
            'targetLabel': 'target',
            'accountId': 'account_id',
            'nextAccountId': 'next_account_id',
            'resourcePackId': 'resource_pack_id',
            # Task 4.66: BD2 pipeline 文件大量使用的 legacy 字段
            'max_wait': 'timeout',
            'condition_variable': 'condition.variable',
            'condition_operator': 'condition.operator',
            'condition_value': 'condition.value',
            'true_node_id': 'true_branch',
            'false_node_id': 'false_branch',
            # Task 4.66: template_match 的 template 字段 (agent legacy, 无 Id 后缀)
            'template': 'template_id',
        }
        # 节点级旧字段 (在 node 顶层, 不在 config 内)
        node_legacy_fields = {
            'action': 'node_type',
            'type': 'node_type',
            'next_step': 'edges',
            'next_node_id': 'edges',  # Task 4.66: BD2 文件常用 next_node_id
            'retry_interval': 'retry.base_delay',
            'fallback_action': 'fallback.action',
        }

        for node in nodes:
            node_id = node.get('id', '')
            node_type = _node_type(node) or ''
            # 1. 检查节点顶层旧字段
            for legacy, canonical in node_legacy_fields.items():
                if legacy in node:
                    results.append(CheckItem(
                        check='legacy_fields',
                        status='fail',
                        message=f"节点 '{node_id}' 含旧字段 '{legacy}', 应改用 '{canonical}' (chain schema 已废弃)",
                        node_id=node_id,
                        suggestion=f"请将 '{legacy}' 改为 '{canonical}'",
                    ))
            # 2. 检查 config 内旧字段
            data = _node_config(node)
            for legacy, canonical in legacy_field_map.items():
                if legacy in data:
                    # Task 4.66: 字段 `template` 仅对 template_match 节点视为 legacy
                    # (其他节点如 wait mode=template 用 template 字段是 canonical, 不是 legacy)
                    if legacy == 'template' and node_type != 'template_match':
                        continue
                    results.append(CheckItem(
                        check='legacy_fields',
                        status='fail',
                        message=f"节点 '{node_id}' config 含旧字段 '{legacy}', 应改用 '{canonical}'",
                        node_id=node_id,
                        suggestion=f"请将 '{legacy}' 改为 '{canonical}'",
                    ))
        return results

    def _check_template_refs(self, nodes: list) -> list[CheckItem]:
        """检查 template_match 节点的 template_id 引用是否已配置。

        Task 3.3 (P2-3): template_id 留空从 warn 升级为 fail。
        原因: 用户照着模板改后若不填 template_id, backend validate 通过
        但执行时 agent 会失败 — 与 N192 B5「校验前置」原则相悖。

        Task 4.2 (P0-3, 2026-07-28): canonical 字段名归一化为 `template_id`
        (snake_case, 与 Python/dataclass 习惯一致, 与 Editor.tsx 保存字段一致)。
        兼容历史字段:
        - `templateId` (canvas schema, camelCase, 老数据)
        - `template` (agent nested schema legacy, 无 Id 后缀, 老数据)
        任一非空即视为配置; 三者都为空 (None 或 '') → fail。
        """
        results = []
        for node in nodes:
            if _node_type(node) != 'template_match':
                continue
            data = _node_config(node)
            # Task 4.2: canonical = template_id; 兼容 templateId (canvas) / template (legacy agent)
            template_id = data.get('template_id')
            template_id_legacy_canvas = data.get('templateId')
            template_legacy_agent = data.get('template')
            if template_id or template_id_legacy_canvas or template_legacy_agent:
                results.append(CheckItem(
                    check='template_refs',
                    status='pass',
                    message=f"节点 '{node.get('id')}' 模板引用存在",
                    node_id=node.get('id'),
                ))
            else:
                # Task 3.3: warn → fail, 避免 backend validate 通过但 agent 执行失败
                results.append(CheckItem(
                    check='template_refs',
                    status='fail',
                    message=f"节点 '{node.get('id')}' template_match 节点必须配置 template_id 字段",
                    node_id=node.get('id'),
                    suggestion='请在资源包中选择一个模板,或填写 base64 编码的模板图像',
                ))
        return results

    def _check_pipeline_refs(self, nodes: list) -> list[CheckItem]:
        """检查 sub_pipeline 节点引用的 Pipeline 是否存在。"""
        results = []
        # N192 性能优化: 先收集所有 pipeline_id, 一次查询避免 N+1
        sub_pipeline_nodes = []
        for node in nodes:
            if _node_type(node) != 'sub_pipeline':
                continue
            sub_pipeline_nodes.append(node)

        # 收集所有非空 pipeline_id
        # Task 4.37 (P0-9, 2026-07-28): _check_pipeline_refs 字段名归一化
        # 同时支持 canonical snake_case (`pipeline_id`) 与 legacy camelCase (`pipelineId`),
        # 与 _check_required_fields line 94 字段名口径保持一致。
        # 之前只读 `pipelineId` → 前端 NodePropertyPanel 写 `pipeline_id` 时校验失效。
        pipeline_ids_to_check = []
        for node in sub_pipeline_nodes:
            data = _node_config(node)
            pipeline_id = data.get('pipeline_id') or data.get('pipelineId')
            if pipeline_id:
                pipeline_ids_to_check.append(pipeline_id)

        # 一次查询所有存在的 pipeline_id
        existing_ids = set()
        if pipeline_ids_to_check:
            existing_ids = set(
                Pipeline.objects.filter(id__in=pipeline_ids_to_check).values_list('id', flat=True)
            )

        # 逐节点判定
        for node in sub_pipeline_nodes:
            data = _node_config(node)
            pipeline_id = data.get('pipeline_id') or data.get('pipelineId')
            if pipeline_id:
                # pipeline_id 可能是 str 或 int, 统一转换后比较
                try:
                    pid_int = int(pipeline_id)
                    exists = pid_int in existing_ids
                except (ValueError, TypeError):
                    exists = False
                if exists:
                    results.append(CheckItem(
                        check='pipeline_refs',
                        status='pass',
                        message=f"节点 '{node.get('id')}' Pipeline 引用存在",
                        node_id=node.get('id'),
                    ))
                else:
                    results.append(CheckItem(
                        check='pipeline_refs',
                        status='fail',
                        message=f"节点 '{node.get('id')}' 引用的 Pipeline({pipeline_id}) 不存在",
                        node_id=node.get('id'),
                        suggestion='请选择有效的 Pipeline',
                    ))
            else:
                results.append(CheckItem(
                    check='pipeline_refs',
                    status='warn',
                    message=f"节点 '{node.get('id')}' 未选择 Pipeline",
                    node_id=node.get('id'),
                ))
        return results

    def _check_connectivity(self, nodes: list, edges: list) -> list[CheckItem]:
        """检查是否存在孤立节点。"""
        results = []
        connected_ids: set = set()
        for edge in edges:
            connected_ids.add(edge.get('source', ''))
            connected_ids.add(edge.get('target', ''))

        for node in nodes:
            node_id = node.get('id', '')
            if len(nodes) > 1 and node_id not in connected_ids:
                results.append(CheckItem(
                    check='connectivity',
                    status='warn',
                    message=f"节点 '{node_id}' ({_node_type(node)}) 是孤立节点，无连线",
                    node_id=node_id,
                    suggestion='请将此节点与其他节点连线',
                ))
            else:
                results.append(CheckItem(
                    check='connectivity',
                    status='pass',
                    message=f"节点 '{node_id}' 连接完整",
                    node_id=node_id,
                ))
        return results

    def _check_entry_exit(self, nodes: list) -> list[CheckItem]:
        """检查 Pipeline 节点总数是否合理（至少 1 个节点）。"""
        results = []
        if len(nodes) == 0:
            results.append(CheckItem(
                check='entry_exit',
                status='fail',
                message='Pipeline 为空，请添加至少一个节点',
                suggestion='从左栏节点库拖拽节点到画布',
            ))
        else:
            results.append(CheckItem(
                check='entry_exit',
                status='pass',
                message=f'Pipeline 包含 {len(nodes)} 个节点',
            ))
        return results
