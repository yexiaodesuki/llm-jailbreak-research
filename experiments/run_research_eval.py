"""
run_research_eval.py (PAIR 迭代反馈实验运行脚本 - 并行增强版)
作用：
1. 实现针对单个有害问题的并行攻击链 (Parallel Chains)。
2. 保持原有的路径规则与数据集适配。
"""

import json
import os
import time
from datetime import datetime
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading # 确保导入了 threading

# 将项目根目录添加到系统路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.attack.improved_query_opt import ImprovedQueryOpt
from src.models.model_api import LocalModel, CloudModel

# --- PAIR 并行参数配置 ---
N_STREAMS = 2  # 并行流数量 (PAIR 论文建议 20，建议你先用 5 测试)
MAX_ITERATIONS = 15  # 每条链的最大迭代次数

def run_single_chain(chain_id, question, target_model, attacker_llm, log_dir, task_id, stop_event):
    """
    运行单条攻击链的辅助函数
    """
    try:
        # 将 stop_event 传进去
        attacker = ImprovedQueryOpt(target_model, attacker_llm=attacker_llm, stop_event=stop_event)
        
        # 为每条链分配独立的日志文件以便回放和研究
        chain_log_path = log_dir / f"task_{task_id}_chain_{chain_id}_trace.jsonl"
        attacker.current_log_path = str(chain_log_path)
        
        if os.path.exists(attacker.current_log_path):
            os.remove(attacker.current_log_path)
            
        try:
            best_prompt, success, queries = attacker.optimize(question, max_iters=MAX_ITERATIONS)
            return {
                "chain_id": chain_id,
                "success": success,
                "queries": queries,
                "prompt": best_prompt
            }
        except Exception as e:
            print(f"      [!] 链 {chain_id} 执行异常: {e}")
            return {"chain_id": chain_id, "success": False, "queries": 0, "prompt": "Error"}
    except Exception as e:
        print(f"[-] Chain {chain_id} 崩溃: {e}")
        return False, 0, "Error"

def main():
    # --- 1. 模型初始化 ---
    try:
        print("\n" + "="*60)
        print("[*] 实验启动：PAIR-Parallel 并行进化引擎")
        print(f"    -> 并行配置: {N_STREAMS} Streams | Max {MAX_ITERATIONS} Iters")
        
        # 获取攻击者和评估者（默认逻辑）
        attacker_llm = CloudModel() 
        
        # --- 修改处：调用交互式选择函数获取目标模型 ---
        from src.models.model_api import get_target_model
        target_model = get_target_model() 
        
        # 根据返回的模型类型动态打印信息
        target_info = "本地 Qwen2.5 (Local)" if isinstance(target_model, LocalModel) else "云端 GLM-4-Flash (Target API)"
        print(f"    -> 攻击者 (Attacker): 智谱AI GLM-4 (Cloud)")
        print(f"    -> 目标模型 (Target): {target_info}")
        print(f"    -> 评估模型 (Judge): 智谱AI GLM-4 (Cloud)")
        
        print("="*60 + "\n")
    except Exception as e:
        print(f"\n[Error] 初始化失败: {e}")
        return

    # --- 2. 目录准备 ---
    res_dir = Path("results") / "final_targeted"
    log_dir = Path("logs") / "final_targeted"
    res_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    # --- 3. 数据加载 ---
    data_path = "data/jailbreakbench_50.json"
    if not os.path.exists(data_path):
        print(f"[Error] 未找到数据集: {data_path}")
        return
    with open(data_path, "r", encoding="utf-8") as f:
        questions_data = json.load(f)

    # --- 4. 实验循环 ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    results_save_path = res_dir / f"pair_parallel_report_{timestamp}.json"
    
    full_results = []
    success_count = 0
    total_queries = 0
    
    for item in questions_data:
        question = item["question"]
        task_id = item.get('id', '999')
        category = item.get('category', 'General')
        
        print(f"\n[Task {task_id}] Category: {category} | Target: {question[:30]}...")
        
        start_t = time.time()
        
        # --- 核心改动：使用 ThreadPoolExecutor 运行并行链 ---
        task_success = False
        task_best_prompt = ""
        task_total_queries = 0
        
        # --- 核心改动：为每个 Task 创建一个独立的停止事件 ---
        task_stop_event = threading.Event()
        
        with ThreadPoolExecutor(max_workers=N_STREAMS) as executor:
            futures = [
                executor.submit(
                    run_single_chain, i, question, target_model, 
                    attacker_llm, log_dir, task_id, task_stop_event # 传入开关
                ) 
                for i in range(N_STREAMS)
            ]
            
            for future in as_completed(futures):
                res = future.result()
                task_total_queries += res["queries"]
                # 只要有一条链成功，标记该 Task 成功
                if res["success"] and not task_success:
                    task_success = True
                    task_best_prompt = res["prompt"]
                    # 按照 PAIR 逻辑，一旦某条链成功，可以考虑取消其他线程（此处简化处理，等待所有完成或自行扩展）
        
        if not task_success:
            task_best_prompt = "All chains failed"

        elapsed = time.time() - start_t
        total_queries += task_total_queries
        if task_success: success_count += 1

        record = {
            "id": task_id,
            "category": category, 
            "question": question,
            "success": task_success,
            "queries_used": task_total_queries,
            "time_cost": round(elapsed, 2),
            "optimized_prompt": task_best_prompt
        }
        full_results.append(record)
        
        status_icon = "✅ SUCCESS" if task_success else "❌ FAILED"
        print(f"--> Result: {status_icon} | Total Queries: {task_total_queries} | Time: {elapsed:.1f}s")

    # --- 5. 统计与汇总 ---
    total_samples = len(questions_data)
    asr = success_count / total_samples if total_samples > 0 else 0
    avg_q = total_queries / total_samples if total_samples > 0 else 0
    
    final_report = {
        "summary": {
            "experiment_type": "PAIR_Parallel_Attack",
            "streams": N_STREAMS,
            "asr": round(asr, 4),
            "avg_queries": round(avg_q, 2),
            "total_samples": total_samples,
            "success_count": success_count
        },
        "details": full_results
    }

    with open(results_save_path, "w", encoding="utf-8") as f:
        json.dump(final_report, f, ensure_ascii=False, indent=4)
        
    print(f"\n[*] 实验完成。报告: {results_save_path}")

if __name__ == "__main__":
    main()