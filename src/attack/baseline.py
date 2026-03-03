# src/attack/baseline.py

def run_baseline(model_func, questions, max_round=3):
    """
    V1 基础多轮调用框架

    参数:
        model_func: 模型调用函数
        questions: 输入问题列表
        max_round: 每个问题最多调用次数

    返回:
        results: 实验结果列表
    """

    results = []

    for q in questions:

        attempts = 0
        responses = []

        for _ in range(max_round):
            attempts += 1
            response = model_func(q)
            responses.append(response)

        results.append({
            "question": q,
            "responses": responses,
            "attempts": attempts
        })

    return results