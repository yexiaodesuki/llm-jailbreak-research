"""
run_query_opt.py (双模型分离版)
作用：
1. 固定使用智谱AI (CloudModel) 作为提示词进化引擎。
2. 固定使用本地模型 (LocalModel) 作为攻击目标。
"""

import json
import os
import time
from datetime import datetime
import sys
from pathlib import Path

# 将项目根目录添加到系统路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.attack.query_opt import QueryOpt
from src.models.model_api import LocalModel, CloudModel

def main():
    # --- 1. 分离初始化模型 ---
    try:
        print("\n" + "="*50)
        print("[*] 环境准备：")
        print("    -> 攻击者 (Evolution Engine): 智谱AI (Cloud)")
        print("    -> 受害者 (Target Model): 本地 Qwen2.5 (Local)")
        
        # 初始化云端模型，用于 PromptGenerator 的进化逻辑
        attacker_llm = CloudModel() 
        
        # 初始化本地模型，作为实验攻击目标
        target_model = LocalModel() 
        
        # 实例化 QueryOpt
        # 注意：这里我们通过构造函数注入 attacker_llm
        attacker = QueryOpt(target_model, attacker_llm=attacker_llm)
        
        # 实验标签
        model_label = "local_targeted" 
        print("="*50 + "\n")
    except Exception as e:
        print(f"\n[Error] 模型加载或连接失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # --- 2. 目录准备 ---
    res_dir = Path("results") / model_label.lower()
    log_dir = Path("logs") / model_label.lower()
    res_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    # --- 3. 数据加载 ---
    data_path = "data/harmful_questions.json"
    if not os.path.exists(data_path):
        print(f"[Error] 未找到数据文件: {data_path}")
        return
        
    with open(data_path, "r", encoding="utf-8") as f:
        questions_data = json.load(f)

    # --- 4. 实验循环 ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    results_save_path = res_dir / f"{model_label}_attacked_by_cloud_{timestamp}.json"
    
    full_results = []
    success_count = 0
    total_queries = 0
    
    print(f"[*] 实验启动 | 样本数: {len(questions_data)}")

    for item in questions_data:
        question = item["question"]
        task_id = item.get('id', '999')
        task_level = item.get('level', 'N/A')
        
        print(f"\n[任务] ID: {task_id} | 等级: {task_level} | 目标: {question[:30]}...")
        
        # 设置日志路径
        attacker.current_log_path = str(log_dir / f"task_{task_id}_trace.jsonl")
        if os.path.exists(attacker.current_log_path):
            os.remove(attacker.current_log_path)

        start_t = time.time()
        
        try:
            # 执行优化
            best_prompt, success, queries = attacker.optimize(
                question, 
                max_iters=3, 
                beam_width=3
            )
        except Exception as e:
            print(f"  [!] 执行异常: {e}")
            best_prompt, success, queries = "Error", False, 0

        elapsed = time.time() - start_t
        total_queries += queries
        if success: success_count += 1

        record = {
            "id": task_id,
            "level": task_level, 
            "question": question,
            "success": success,
            "queries_used": queries,
            "time_cost": round(elapsed, 2),
            "optimized_prompt": best_prompt
        }
        full_results.append(record)
        print(f"--> 结果: {'✅' if success else '❌'} | 查询: {queries} | 耗时: {elapsed:.1f}s")

    # --- 5. 保存与统计 ---
    total_samples = len(questions_data)
    final_report = {
        "summary": {
            "target": "Local",
            "attacker": "Cloud_GLM4",
            "asr": success_count / total_samples if total_samples > 0 else 0,
            "avg_queries": total_queries / total_samples if total_samples > 0 else 0
        },
        "details": full_results
    }

    with open(results_save_path, "w", encoding="utf-8") as f:
        json.dump(final_report, f, ensure_ascii=False, indent=4)
    print(f"\n[!] 实验完成。报告已保存至: {results_save_path}")

if __name__ == "__main__":
    main()