"""Pipeline 节点类型集合

C22 fix: 显式 import 各节点模块以触发 `@register_node` 副作用注册。
此前各节点模块只在被测试或被生产代码单独 import 时才会注册，导致
`PipelineNodeType` 中声明但生产路径未 import 的类型在解析时报
`未知的节点类型` 错误。
"""

# Detection / recognition
# Input actions
# Composite / maa actions
# Control flow
# Device / app lifecycle
# Notifications
from . import (  # noqa: F401  # noqa: F401  # noqa: F401  # noqa: F401  # noqa: F401
    app_control,
    branch,
    click,
    color_detect,
    composite_match,
    device_control,
    direct_hit,
    feature_match,
    goto,
    key_press,
    log_message,  # TD-350: 示例节点，演示元数据注册机制的可扩展性
    long_press,
    loop,
    maa_actions,
    monitor,
    multi_scroll,
    multi_swipe,
    multi_touch,
    neural_network,
    nn_recognition,
    notify,  # noqa: F401
    ocr,
    random_delay,
    roi_resolver,
    sort_select,
    sub_pipeline,
    swipe,
    swipe_until,
    template_match,
    template_match_any,
    text_input,
    uia_control,  # spec-2026-08-26 P2: UIAutomation 语义节点
    wait,
    wheel,
)
