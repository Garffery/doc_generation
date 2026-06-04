"""示例：使用 ResilientModel 处理结构化输出失败的情况。"""

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

from doc_generation.resilience.config import ResilienceConfig
from doc_generation.resilience.invoker import ResilientModel


class CodeAnalysis(BaseModel):
    """代码分析结果结构。"""

    summary: str = Field(description="代码功能摘要")
    complexity: int = Field(description="复杂度评分 1-10")
    suggestions: list[str] = Field(description="改进建议列表")


def main():
    # 1. 创建配置
    config = ResilienceConfig.from_yaml("config.yml")

    # 2. 创建基础模型
    base_model = ChatOpenAI(model="gpt-4", temperature=0)

    # 3. 包装为弹性模型
    resilient_model = ResilientModel(base_model, role="analyzer", config=config)

    # 4. 应用结构化输出（此时 expected_schema 会被自动设置）
    structured_model = resilient_model.with_structured_output(CodeAnalysis)

    # 5. 调用模型
    messages = [
        {"role": "system", "content": "You are a code analysis expert."},
        {"role": "user", "content": "Analyze this code: def hello(): print('world')"}
    ]

    try:
        result = structured_model.invoke(messages)

        # 如果模型返回了 AIMessage 而不是 CodeAnalysis：
        # 1. ResilientModel 检测到类型不匹配
        # 2. 自动添加提示："IMPORTANT: You MUST respond with the exact structured format..."
        # 3. 重试一次
        # 4. 如果仍失败，触发 fallback 链

        print(f"分析结果: {result.summary}")
        print(f"复杂度: {result.complexity}/10")
        print(f"建议: {', '.join(result.suggestions)}")

    except Exception as e:
        print(f"分析失败: {e}")


if __name__ == "__main__":
    main()
