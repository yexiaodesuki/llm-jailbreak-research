"""
run_query_opt.py
作用：自动化批量运行攻击实验并保存结果。
注意：本脚本已集成指标计算，无需外部 metrics.py 支持，确保直接运行。
"""

import json
import os
import time
from datetime import datetime
import sys

# 将项目根目录添加到系统路径，确保能找到 src 文件夹
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.attack.query_opt import QueryOpt
from src.models.model_api import LocalModel

def main():
    # --- 1. 检查环境与目录 ---
    if not os.path.exists("results"):
        os.makedirs("results")
    if not os.path.exists("logs"):
        os.makedirs("logs")

    # --- 2. 初始化模型与攻击器 ---
    # 这一步会触发 Qwen 模型的加载（需要几分钟）
    try:
        model = LocalModel()
        attacker = QueryOpt(model)
    except Exception as e:
        print(f"[Error] 模型加载失败，请检查显存或模型路径: {e}")
        return

    # --- 3. 加载测试数据 ---
    data_path = "data/harmful_questions.json"
    if not os.path.exists(data_path):
        print(f"[Error] 未找到数据文件: {data_path}")
        return
        
    with open(data_path, "r", encoding="utf-8") as f:
        questions_data = json.load(f)

    # --- 4. 开始实验循环 ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    results_save_path = f"results/baseline_run_{timestamp}.json"
    
    full_results = []
    success_count = 0
    total_queries = 0
    
    print(f"\n[*] 实验启动 | 样本总数: {len(questions_data)}")
    print(f"[*] 输出文件: {results_save_path}")
    print(f"[*] 轨迹日志: logs/task_[ID]_trace.jsonl (用于展示系统读取)") # 明确告知日志去向
    print("=" * 60)

    for item in questions_data:
        question = item["question"]
        task_id = item.get('id') # 获取 ID
        print(f"\n[任务] ID: {task_id} | 目标问题: {question}")
        
        # --- [新增：不改动逻辑，仅指定日志路径] ---
        # 为当前任务分配唯一的轨迹日志文件，方便 app.py 精确读取回放
        detail_log_path = f"logs/task_{task_id}_trace.jsonl"
        attacker.current_log_path = detail_log_path
        
        # 每次运行前清空旧的轨迹文件，确保 app.py 显示的是最新的结果
        if os.path.exists(detail_log_path):
            os.remove(detail_log_path)
        # ------------------------------------------

        start_t = time.time()
        
        # 调用我们完善后的 Beam Search 优化方法
        # 逻辑完全保持原样，仅在内部执行时会根据 current_log_path 自动写日志
        best_prompt, success, queries = attacker.optimize(
            question, 
            max_iters=3, 
            beam_width=3
        )
        
        elapsed = time.time() - start_t
        total_queries += queries
        if success:
            success_count += 1

        # 记录详细数据
        record = {
            "id": task_id,
            "question": question,
            "success": success,
            "queries_used": queries,
            "time_cost": round(elapsed, 2),
            "optimized_prompt": best_prompt
        }
        full_results.append(record)
        
        # 间隔打印，防止刷屏
        status = "✅ 成功" if success else "❌ 失败"
        print(f"--> 结果: {status} | 查询数: {queries} | 耗时: {elapsed:.1f}s")

    # --- 5. 计算指标并持久化 ---
    asr = success_count / len(questions_data) if questions_data else 0
    avg_queries = total_queries / len(questions_data) if questions_data else 0

    final_report = {
        "summary": {
            "timestamp": timestamp,
            "total_samples": len(questions_data),
            "attack_success_rate": asr,
            "average_queries": avg_queries,
            "total_success": success_count
        },
        "details": full_results
    }

    with open(results_save_path, "w", encoding="utf-8") as f:
        json.dump(final_report, f, ensure_ascii=False, indent=4)

    # --- 6. 最终结果陈述 ---
    print("\n" + "=" * 20 + " 实验统计结果 " + "=" * 20)
    print(f"1. ASR (攻击成功率): {asr * 100:.2f}%")
    print(f"2. AvgQ (平均查询次数): {avg_queries:.2f}")
    print(f"3. 报告文件已生成，请在 results 目录下查看。")
    print("=" * 55)

if __name__ == "__main__":
    main()