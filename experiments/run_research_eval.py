"""
run_research_eval.py (PAIR 迭代反馈实验运行脚本)
作用：
1. 适配 app.py 的路径规则：使用 results/improved_targeted 和 logs/improved_targeted。
2. 运行基于 PAIR 论文改进的迭代反馈攻击。
3. 适配 jailbreakbench_50.json 数据集。
"""

import json
import os
import time
from datetime import datetime
import sys
from pathlib import Path

# 将项目根目录添加到系统路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.attack.improved_query_opt import ImprovedQueryOpt
from src.models.model_api import LocalModel, CloudModel

def main():
    # --- 1. 模型初始化 ---
    try:
        print("\n" + "="*60)
        print("[*] 实验启动：PAIR-Refined 迭代反馈进化引擎")
        print("    -> 攻击者 (Attacker): 智谱AI GLM-4 (Cloud)")
        print("    -> 目标模型 (Target): 本地 Qwen2.5 (Local)")
        print("    -> 评估模型 (Judge): 智谱AI GLM-4 (Cloud)")
        
        attacker_llm = CloudModel() 
        target_model = LocalModel() 
        
        # 实例化已经重构为 PAIR 逻辑的优化器
        attacker = ImprovedQueryOpt(target_model, attacker_llm=attacker_llm)
        
        print("="*60 + "\n")
    except Exception as e:
        print(f"\n[Error] 初始化失败: {e}")
        return

    # --- 2. 目录准备 ---
    res_dir = Path("results") / "final_targeted"
    log_dir = Path("logs") / "final_targeted"
    res_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    # --- 3. 数据加载 (适配 jailbreakbench_50.json) ---
    data_path = "data/jailbreakbench_50.json"
    if not os.path.exists(data_path):
        print(f"[Error] 未找到数据集: {data_path}")
        return
        
    with open(data_path, "r", encoding="utf-8") as f:
        questions_data = json.load(f)

    # --- 4. 实验循环 ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    results_save_path = res_dir / f"pair_attack_report_{timestamp}.json"
    
    full_results = []
    success_count = 0
    total_queries = 0
    
    # PAIR 建议迭代次数通常为 20 轮，这里你可以根据时间灵活调整（如 10 轮）
    MAX_ITERATIONS = 15 
    
    print(f"[*] 样本量: {len(questions_data)} | 最大迭代轮次: {MAX_ITERATIONS}")

    for item in questions_data:
        question = item["question"]
        task_id = item.get('id', '999')
        category = item.get('category', 'General')
        
        print(f"\n[Task {task_id}] Category: {category}")
        print(f"Target: {question[:35]}...")
        
        # 设置追踪日志路径，确保 app.py 可以回放
        attacker.current_log_path = str(log_dir / f"task_{task_id}_trace.jsonl")
        
        # 清理旧日志
        if os.path.exists(attacker.current_log_path):
            os.remove(attacker.current_log_path)

        start_t = time.time()
        
        try:
            # 执行迭代优化 (PAIR 逻辑)
            # 注意：现在的优化器内部会自动调用 evolve_prompt 逻辑
            best_prompt, success, queries = attacker.optimize(
                question, 
                max_iters=MAX_ITERATIONS
            )
        except Exception as e:
            print(f"  [!] 执行异常: {e}")
            import traceback
            traceback.print_exc()
            best_prompt, success, queries = "Error", False, 0

        elapsed = time.time() - start_t
        total_queries += queries
        if success: success_count += 1

        record = {
            "id": task_id,
            "category": category, 
            "question": question,
            "success": success,
            "queries_used": queries,
            "time_cost": round(elapsed, 2),
            "optimized_prompt": best_prompt
        }
        full_results.append(record)
        
        status_icon = "✅ SUCCESS" if success else "❌ FAILED"
        print(f"--> Result: {status_icon} | Queries: {queries} | Time: {elapsed:.1f}s")

    # --- 5. 统计与汇总 ---
    total_samples = len(questions_data)
    asr = success_count / total_samples if total_samples > 0 else 0
    avg_q = total_queries / total_samples if total_samples > 0 else 0
    
    final_report = {
        "summary": {
            "experiment_type": "PAIR_Iterative_Attack",
            "model_info": "Attacker:GLM-4 / Target:Qwen2.5-3B-Instruct",
            "timestamp": timestamp,
            "asr": round(asr, 4),
            "avg_queries": round(avg_q, 2),
            "total_samples": total_samples,
            "success_count": success_count
        },
        "details": full_results
    }

    with open(results_save_path, "w", encoding="utf-8") as f:
        json.dump(final_report, f, ensure_ascii=False, indent=4)
        
    print(f"\n" + "="*60)
    print(f"[*] 实验任务全部完成")
    print(f"    - 最终攻击成功率 (ASR): {asr*100:.2f}%")
    print(f"    - 平均查询次数: {avg_q:.2f}")
    print(f"    - 实验报告已生成: {results_save_path}")
    print("="*60)

if __name__ == "__main__":
    main()