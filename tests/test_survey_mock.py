"""
问卷调研系统测试

使用Mock后端进行开发测试。
"""

import asyncio
from src.survey import (
    SurveyClient,
    QuestionType,
    SurveyStatus,
    BackendFactory,
)


async def test_mock_backend():
    """测试Mock后端"""
    
    print("=" * 50)
    print("问卷调研系统 - Mock后端测试")
    print("=" * 50)
    
    # 1. 创建客户端
    print("\n[1] 创建Mock客户端...")
    client = SurveyClient(backend_type="mock")
    
    # 2. 列出可用后端
    print("\n[2] 可用后端列表:")
    backends = BackendFactory.list_available()
    for b in backends:
        print(f"  - {b['type']}: {b['name']}")
    
    # 3. 创建问卷
    print("\n[3] 创建问卷...")
    survey = await client.create_survey(
        title="用户满意度调研",
        questions=[
            {
                "id": "q1",
                "text": "您的性别？",
                "type": "single_choice",
                "options": ["男", "女"],
                "required": True,
            },
            {
                "id": "q2",
                "text": "您的年龄段？",
                "type": "single_choice",
                "options": ["18-25岁", "26-35岁", "36-50岁", "50岁以上"],
            },
            {
                "id": "q3",
                "text": "您的满意度评分？",
                "type": "scale",
                "validation_rules": {"scale_min": 1, "scale_max": 5},
            },
            {
                "id": "q4",
                "text": "您使用过哪些功能？",
                "type": "multiple_choice",
                "options": ["功能A", "功能B", "功能C", "功能D"],
            },
            {
                "id": "q5",
                "text": "您的建议？",
                "type": "open_ended",
            },
        ],
        description="感谢您参与本次调研！",
    )
    print(f"  问卷ID: {survey.survey_id}")
    print(f"  问题数量: {len(survey.questions)}")
    
    # 4. 发放问卷
    print("\n[4] 发放问卷...")
    task = await client.distribute(survey, target_count=100)
    print(f"  任务ID: {task.task_id}")
    print(f"  外部ID: {task.external_id}")
    print(f"  问卷链接: {task.share_url}")
    print(f"  状态: {task.status.value}")
    
    # 5. 生成模拟回答
    print("\n[5] 生成模拟回答...")
    mock_backend = BackendFactory.get_or_create("mock")
    responses = await mock_backend.generate_mock_responses(task.external_id, count=20)
    print(f"  生成数量: {len(responses)}")
    
    # 6. 获取统计信息
    print("\n[6] 获取统计信息...")
    stats = await client.get_statistics(task)
    print(f"  总浏览量: {stats.get('total_views', 0)}")
    print(f"  开始填写: {stats.get('total_starts', 0)}")
    print(f"  完成数: {stats.get('total_completes', 0)}")
    print(f"  完成率: {stats.get('completion_rate', 0):.1%}")
    
    # 7. 获取回答数据
    print("\n[7] 获取回答数据...")
    results = await client.get_results(task, limit=5)
    print(f"  获取数量: {len(results)}")
    
    if results:
        print("\n  示例回答:")
        resp = results[0]
        print(f"    回答ID: {resp.response_id}")
        print(f"    答题时长: {resp.duration_seconds}秒")
        print(f"    质量分数: {resp.quality_score:.2f}")
        for qid, ans in list(resp.answers.items())[:3]:
            print(f"    {qid}: {ans.answer_value}")
    
    # 8. 测试状态
    print("\n[8] 测试状态查询...")
    status = await client.get_status(task)
    print(f"  当前状态: {status.value}")
    
    # 9. 测试暂停/恢复
    print("\n[9] 测试暂停/恢复...")
    await client.task_manager.pause_task(task.task_id)
    task = await client.task_manager.get_task(task.task_id)
    print(f"  暂停后状态: {task.status.value}")
    
    await client.task_manager.resume_task(task.task_id)
    task = await client.task_manager.get_task(task.task_id)
    print(f"  恢复后状态: {task.status.value}")
    
    # 10. 测试关闭
    print("\n[10] 测试关闭问卷...")
    await client.close(task)
    print("  已关闭")
    
    print("\n" + "=" * 50)
    print("测试完成！")
    print("=" * 50)
    
    return True


async def test_backend_options():
    """测试后端选项展示"""
    
    print("\n" + "=" * 50)
    print("后端选项展示")
    print("=" * 50)
    
    options = SurveyClient.get_backend_options()
    
    for backend_type, info in options.items():
        print(f"\n[{info['name']}]")
        print(f"  类型: {info['type']}")
        print(f"  优点: {', '.join(info['pros'])}")
        print(f"  缺点: {', '.join(info['cons'])}")
        print(f"  成本: {info['cost']}")
        print(f"  周期: {info['duration']}")


if __name__ == "__main__":
    print("\n开始测试...\n")
    
    # 运行测试
    asyncio.run(test_mock_backend())
    
    # 展示后端选项
    asyncio.run(test_backend_options())