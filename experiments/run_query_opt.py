"""
run_query_opt.py (适配版)
作用：支持交互式模型选择（本地/智谱AI），自动化运行实验并按模型分类保存日志。
适配点：增加有害分级(Level)持久化，支持 App.py 的分类 ASR 统计。
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
from src.models.model_api import get_model

def main():
    # --- 1. 交互式初始化模型 ---
    try:
        model, model_label = get_model() 
        attacker = QueryOpt(model)
    except Exception as e:
        print(f"\n[Error] 模型加载或连接失败: {e}")
        return

    # --- 2. 检查并创建分级目录 (确保路径跨平台兼容) ---
    # 结果存放在 results/local/ 或 results/cloud/
    # 轨迹存放在 logs/local/ 或 logs/cloud/
    res_dir = Path("results") / model_label.lower()
    log_dir = Path("logs") / model_label.lower()
    
    res_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    # --- 3. 加载测试数据 ---
    data_path = "data/harmful_questions.json"
    if not os.path.exists(data_path):
        print(f"[Error] 未找到数据文件: {data_path}")
        return
        
    with open(data_path, "r", encoding="utf-8") as f:
        questions_data = json.load(f)

    # --- 4. 开始实验循环 ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    results_save_path = res_dir / f"{model_label}_run_{timestamp}.json"
    
    full_results = []
    success_count = 0
    total_queries = 0
    
    print(f"\n[*] 实验启动 | 目标模型: {model_label.upper()}")
    print(f"[*] 样本总数: {len(questions_data)}")
    print(f"[*] 输出文件: {results_save_path}")
    print(f"[*] 轨迹目录: {log_dir}/task_[ID]_trace.jsonl")
    print("=" * 60)

    for item in questions_data:
        question = item["question"]
        task_id = item.get('id', '999')
        task_level = item.get('level', 'N/A') # 提取有害梯度 L1/L2/L3
        
        print(f"\n[任务] ID: {task_id} | 等级: {task_level} | 目标: {question[:30]}...")
        
        # 指定分类后的轨迹日志路径
        detail_log_path = log_dir / f"task_{task_id}_trace.jsonl"
        attacker.current_log_path = str(detail_log_path)
        
        # 清空旧日志并确保目录存在
        if detail_log_path.exists():
            detail_log_path.unlink()

        start_t = time.time()
        
        # 执行优化算法 (增加超时或异常捕获以应对云端 400 错误)
        try:
            # 这里调用 QueryOpt 的优化逻辑，max_iters/beam_width 根据实验需求调整
            best_prompt, success, queries = attacker.optimize(
                question, 
                max_iters=3, 
                beam_width=3
            )
        except Exception as e:
            # 这里的异常捕获非常重要，防止云端 WAF 的硬报错中断整个批量实验
            print(f"  [!] 算法执行异常 (可能为网关硬拦截): {e}")
            best_prompt, success, queries = "Blocked by WAF/Policy", False, 1

        elapsed = time.time() - start_t
        total_queries += queries
        if success:
            success_count += 1

        # 记录详细数据（关键：增加 level 和 category 字段，供 App.py 统计）
        record = {
            "id": task_id,
            "level": task_level, 
            "category": item.get("category", "Unknown"),
            "question": question,
            "success": success,
            "queries_used": queries,
            "time_cost": round(elapsed, 2),
            "optimized_prompt": best_prompt
        }
        full_results.append(record)
        
        status = "✅ 成功" if success else "❌ 失败"
        print(f"--> 结果: {status} | 查询数: {queries} | 耗时: {elapsed:.1f}s")

    # --- 5. 计算指标并持久化 ---
    total_samples = len(questions_data)
    asr = success_count / total_samples if total_samples > 0 else 0
    avg_queries = total_queries / total_samples if total_samples > 0 else 0

    final_report = {
        "summary": {
            "model_type": model_label,
            "timestamp": timestamp,
            "total_samples": total_samples,
            "attack_success_rate": asr,
            "average_queries": avg_queries,
            "total_success": success_count
        },
        "details": full_results
    }

    with open(results_save_path, "w", encoding="utf-8") as f:
        json.dump(final_report, f, ensure_ascii=False, indent=4)

    # --- 6. 最终统计结果 ---
    print("\n" + "=" * 20 + f" {model_label.upper()} 实验统计 " + "=" * 20)
    print(f"1. ASR (总攻击成功率): {asr * 100:.2f}%")
    print(f"2. 分级成功率统计 (ASR by Level):")
    # 简单的控制台分级统计打印
    for lv in ["L1", "L2", "L3"]:
        lv_res = [r['success'] for r in full_results if r['level'] == lv]
        if lv_res:
            lv_asr = sum(lv_res) / len(lv_res)
            print(f"   - {lv}: {lv_asr*100:.1f}% ({sum(lv_res)}/{len(lv_res)})")
            
    print(f"3. 报告保存至: {results_save_path}")
    print("=" * 60)

if __name__ == "__main__":
    main()