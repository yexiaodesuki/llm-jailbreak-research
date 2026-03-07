"""
run_improved_query_opt.py (改进版实验运行脚本)
作用：
1. 适配 app.py 的路径规则：使用 results/improved_targeted 和 logs/improved_targeted。
2. 使用 ImprovedQueryOpt (Thompson Sampling + 语义解耦引擎)。
3. 自动记录策略分布统计，供回放系统分析。
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
        print("[*] 改进版实验启动：MEGA-Opt 自适应进化引擎")
        print("    -> 进化代理 (Attacker): 智谱AI (Cloud)")
        print("    -> 实验目标 (Victim): 本地 Qwen2.5 (Local)")
        
        attacker_llm = CloudModel() 
        target_model = LocalModel() 
        
        # 实例化改进版优化器
        attacker = ImprovedQueryOpt(target_model, attacker_llm=attacker_llm)
        
        print("="*60 + "\n")
    except Exception as e:
        print(f"\n[Error] 初始化失败: {e}")
        return

    # --- 2. 目录准备 (关键修改：适配 app.py 的 improved_targeted 路径) ---
    res_dir = Path("results") / "improved_targeted"
    log_dir = Path("logs") / "improved_targeted"
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
    # 文件名建议包含 model 信息以便区分
    results_save_path = res_dir / f"mega_attack_report_{timestamp}.json"
    
    full_results = []
    success_count = 0
    total_queries = 0
    
    print(f"[*] 样本量: {len(questions_data)} | 运行参数: max_iters=3, beam_width=3")

    for item in questions_data:
        question = item["question"]
        task_id = item.get('id', '999')
        task_level = item.get('level', 'N/A')
        
        print(f"\n[Task {task_id}] Level: {task_level} | Target: {question[:25]}...")
        
        # 设置追踪日志路径 (关键修改：必须符合 task_{id}_trace.jsonl 格式以便 app.py 识别)
        attacker.current_log_path = str(log_dir / f"task_{task_id}_trace.jsonl")
        
        # 如果旧日志存在则清理，确保回放的是最新数据
        if os.path.exists(attacker.current_log_path):
            os.remove(attacker.current_log_path)

        start_t = time.time()
        
        try:
            # 执行 MEGA 优化
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
        
        status_icon = "✅" if success else "❌"
        print(f"--> Result: {status_icon} | Q: {queries} | T: {elapsed:.1f}s")

    # --- 5. 统计与汇总 ---
    total_samples = len(questions_data)
    asr = success_count / total_samples if total_samples > 0 else 0
    avg_q = total_queries / total_samples if total_samples > 0 else 0
    
    final_report = {
        "summary": {
            "experiment_type": "MEGA_Improved_Attack",
            "timestamp": timestamp,
            "asr": round(asr, 4),
            "avg_queries": round(avg_q, 2),
            # 记录策略统计，这在 app.py 的“策略空间”分析中很有用
            "strategy_distribution": getattr(attacker, 'strategy_stats', {})
        },
        "details": full_results
    }

    with open(results_save_path, "w", encoding="utf-8") as f:
        json.dump(final_report, f, ensure_ascii=False, indent=4)
        
    print(f"\n" + "="*60)
    print(f"[*] 实验完成")
    print(f"    - 攻击成功率 (ASR): {asr*100:.2f}%")
    print(f"    - 平均查询次数: {avg_q:.2f}")
    print(f"    - 报告已存至: {results_save_path}")
    print("="*60)

if __name__ == "__main__":
    main()