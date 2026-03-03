# src/main.py

import json
import os

from models.model_api import query_model
from attack.baseline import run_baseline
from utils.metrics import calculate_average_queries, count_samples


def load_data(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():

    # 数据路径
    data_path = os.path.join("data", "harmful_questions.json")

    # 读取问题
    questions = load_data(data_path)

    # 运行V1基线
    results = run_baseline(
        model_func=query_model,
        questions=questions,
        max_round=3
    )

    # 计算指标
    avg_queries = calculate_average_queries(results)
    total = count_samples(results)

    # 输出
    print("===== V1 Baseline 实验结果 =====")
    print("样本数量:", total)
    print("平均调用次数:", avg_queries)


if __name__ == "__main__":
    main()