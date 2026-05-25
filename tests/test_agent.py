#***********************************************
#      Filename: test_agent.py
#   Description: 集成测试：调用 agent_builder 中的顶层智能体
#***********************************************

import asyncio
import pytest
from langchain_core.messages import HumanMessage

from doc_generation.utils import load_dotenv_if_present
load_dotenv_if_present()

from doc_generation.agent_builder import agent
from doc_generation.logging_config import configure_logging

configure_logging()


@pytest.mark.asyncio
async def test_agent_full_pipeline():
    """端到端测试：输入用户需求，验证最终技术开发文档非空。"""
    user_query = """
    游戏中需要开发一个战令活动,这个战令总共有三档,一档免费战令,"进阶福利","天降豪礼"这两档付费直购战令。
活动逻辑: 1.点击战令入口，弹出战令界面，显示战令的奖励,能领取的奖励高亮,未达到领取条件的奖励置灰。
         2. 点击战令界面上的物品，如果有满足战令等级的奖励，会一次性全部领取
         3.如果没有购买"进阶福利"和"天降豪礼",则只能领取免费战令对应的奖励
战令等级:
		战令一共有15个等级，玩家没累计1000积分可以提升一个等级

积分:
	在游戏中完成相应的任务，能够获得对应任务的积分。

活动结算:
	如果活动结束的时候,玩家存在满足领取条件的奖励，但是未领取，需要通过邮件补发的方式进行奖励补发。
    """

    result = await agent.ainvoke({
        "messages": [HumanMessage(content=user_query)]
    })

    assert result.get("final_report"), "final_report 不应为空"
    assert result.get("research_brief"), "research_brief 不应为空"
    assert result.get("draft_report"), "draft_report 不应为空"

    print("\n===== research_brief =====")
    print(result["research_brief"])
    print("\n===== draft_report =====")
    print(result["draft_report"])
    print("\n===== final_report =====")
    print(result["final_report"])


if __name__ == "__main__":
    asyncio.run(test_agent_full_pipeline())
