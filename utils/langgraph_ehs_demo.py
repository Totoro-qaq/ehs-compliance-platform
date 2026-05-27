"""
LangGraph EHS 评估工作流演示脚本

图结构：
  [START] → retrieve → generate → check_result → [END]
                                      ↓ (缺少 risks)
                                   generate (重试，最多 3 次)

状态使用 TypedDict 定义，包含：
- document_text: 待评估的原始文本
- retrieved_context: 检索节点召回的参考标准
- generated_json: 生成节点输出的 JSON 字符串
- parsed_result: 解析后的字典
- retry_count: 当前重试次数
- error: 错误信息
"""

from __future__ import annotations

import json
import random
from typing import TypedDict

from langgraph.graph import END, StateGraph


# ===== 状态定义 =====
class EHSState(TypedDict):
    document_text: str
    retrieved_context: str
    generated_json: str
    parsed_result: dict | None
    retry_count: int
    error: str


# ===== 模拟知识库（检索节点用） =====
MOCK_STANDARDS = [
    "TEST-EHS-001 测试作业控制要求：产生测试颗粒物的工艺设备应设置有效控制系统。",
    "TEST-EHS-002 测试接触限值要求：测试颗粒物 TWA 为 10 test-unit。",
    "TEST-EHS-003 测试物料暂存要求：测试物料应存放在专用容器中。",
    "TEST-EHS-004 测试防护用品要求：接触测试颗粒物作业应配备适用防护用品。",
]


# ===== 节点函数 =====
def retrieve_node(state: EHSState) -> dict:
    """检索节点：根据文档文本模拟 RAG 召回相关测试条款。"""
    print("\n" + "=" * 60)
    print("📚 [检索节点] 正在召回相关测试条款...")
    print(f"   输入文本片段: {state['document_text'][:80]}...")

    # 模拟检索：随机选取 2-3 条标准
    context = "\n".join(random.sample(MOCK_STANDARDS, k=min(3, len(MOCK_STANDARDS))))
    print(f"   召回 {context.count(chr(10)) + 1} 条相关标准")
    print("=" * 60)

    return {"retrieved_context": context}


def generate_node(state: EHSState) -> dict:
    """生成节点：模拟 LLM 根据检索结果生成 EHS 评估 JSON。"""
    retry = state.get("retry_count", 0)
    print("\n" + "=" * 60)
    print(f"🤖 [生成节点] 正在生成评估结果... (第 {retry + 1} 次尝试)")

    # 模拟 LLM 输出：前两次故意缺少 risks 字段以演示重试机制
    if retry < 2:
        # 模拟不完整输出
        result = json.dumps({
            "summary": "该工段存在测试颗粒物积聚和防护不足的问题，需要整改。",
            "metadata": {"model": "mock-llm", "attempt": retry + 1},
            # 故意不包含 risks 字段
        }, ensure_ascii=False)
        print("   ⚠️  生成结果缺少 risks 字段（模拟不完整输出）")
    else:
        # 第三次生成完整结果
        result = json.dumps({
            "risks": [
                {
                    "violated_standard": "TEST-EHS-001 测试作业控制要求",
                    "severity": "HIGH",
                    "evidence": "测试设备未见局部控制装置，现场有测试颗粒物积聚",
                    "recommendation": "立即加装局部控制装置并接入处理系统",
                },
                {
                    "violated_standard": "TEST-EHS-004 测试防护用品要求",
                    "severity": "HIGH",
                    "evidence": "岗位配发一次性测试用品，未见适用防护器",
                    "recommendation": "停用不适用防护用品，配发测试颗粒物防护器",
                },
                {
                    "violated_standard": "TEST-EHS-003 测试物料暂存要求",
                    "severity": "MEDIUM",
                    "evidence": "测试工位 2m 内有敞口存放的测试边角料",
                    "recommendation": "移至专用防火防潮容器，远离火源",
                },
            ],
            "summary": "该工段存在三项测试风险：颗粒物积聚无有效控制、防护用品不适用、测试物料存放不规范。需立即整改。",
            "metadata": {"model": "mock-llm", "attempt": retry + 1},
        }, ensure_ascii=False)
        print(f"   ✅ 生成完整结果（包含 {3} 条风险项）")

    print("=" * 60)
    return {"generated_json": result, "retry_count": retry + 1}


def check_result(state: EHSState) -> dict:
    """校验节点：解析 JSON 并检查是否包含 risks 字段。"""
    print("\n" + "=" * 60)
    print("🔍 [校验节点] 正在验证生成结果...")

    raw = state.get("generated_json", "")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"   ❌ JSON 解析失败: {e}")
        return {"parsed_result": None, "error": f"JSON 解析失败: {e}"}

    if "risks" not in parsed:
        print(f"   ❌ 缺少 risks 字段！当前 keys: {list(parsed.keys())}")
        print(f"   📊 已重试 {state.get('retry_count', 0)} 次")
        return {"parsed_result": None, "error": "缺少 risks 字段"}

    if not isinstance(parsed["risks"], list):
        print("   ❌ risks 字段不是数组")
        return {"parsed_result": None, "error": "risks 字段不是数组"}

    print(f"   ✅ 校验通过！包含 {len(parsed['risks'])} 条风险项")
    print(f"   📝 摘要: {parsed.get('summary', '-')[:60]}...")
    print("=" * 60)
    return {"parsed_result": parsed, "error": ""}


# ===== 条件路由 =====
def should_retry(state: EHSState) -> str:
    """判断是否需要重试生成节点。"""
    if state.get("parsed_result") and not state.get("error"):
        return "done"
    if state.get("retry_count", 0) >= 3:
        print("\n   ⛔ 已达最大重试次数 (3)，放弃重试")
        return "max_retries"
    print("\n   🔄 结果不合格，路由回生成节点重试...")
    return "retry"


# ===== 构建图 =====
def build_graph() -> StateGraph:
    graph = StateGraph(EHSState)

    # 添加节点
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    graph.add_node("check_result", check_result)

    # 定义边
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "check_result")

    # 条件路由：校验后决定是结束还是重试
    graph.add_conditional_edges(
        "check_result",
        should_retry,
        {
            "done": END,
            "retry": "generate",
            "max_retries": END,
        },
    )

    return graph.compile()


# ===== 主入口 =====
def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║        LangGraph EHS 合规评估工作流 - 演示脚本             ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print("║  图结构: retrieve → generate → check_result → END/retry    ║")
    print("║  重试策略: 缺少 risks 字段时自动路由回 generate (最多3次)  ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    # 构建工作流
    workflow = build_graph()

    # 初始状态
    initial_state: EHSState = {
        "document_text": (
            "铸件打磨车间现场检查记录：砂轮机侧墙设有轴流风机排风，"
            "未见明显局部控制装置连接至处理系统。地面有少量测试颗粒物积聚，"
            "清扫频次记录为每周一次。岗位配发一次性纱布口罩。"
            "测试工位 2m 内有敞口存放的测试边角料约 5kg。"
        ),
        "retrieved_context": "",
        "generated_json": "",
        "parsed_result": None,
        "retry_count": 0,
        "error": "",
    }

    print(f"\n📄 输入文档:\n   {initial_state['document_text']}\n")

    # 执行工作流
    final_state = workflow.invoke(initial_state)

    # 打印最终结果
    print("\n")
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║                      最终执行结果                           ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"\n总尝试次数: {final_state['retry_count']}")
    print(f"最终状态: {'✅ 成功' if final_state.get('parsed_result') else '❌ 失败'}")

    if final_state.get("parsed_result"):
        result = final_state["parsed_result"]
        print(f"\n📊 评估摘要:\n   {result['summary']}")
        print(f"\n🚨 风险项 ({len(result['risks'])} 条):")
        for i, risk in enumerate(result["risks"], 1):
            print(f"\n   [{i}] {risk['violated_standard']}")
            print(f"       严重等级: {risk['severity']}")
            print(f"       现场证据: {risk['evidence']}")
            print(f"       整改建议: {risk['recommendation']}")
    else:
        print(f"\n错误信息: {final_state.get('error', '未知错误')}")

    print("\n" + "─" * 62)
    print("工作流执行完毕。")


if __name__ == "__main__":
    main()
