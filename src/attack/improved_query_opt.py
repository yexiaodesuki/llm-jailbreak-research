import time
import json
import threading  # 引入锁机制，确保并行写入日志不冲突
from src.attack.query_opt import QueryOpt

# 定义一个全局锁，用于多线程文件写入
file_lock = threading.Lock()

class ImprovedQueryOpt(QueryOpt):
    """
    完全参照 PAIR (Prompt Automatic Iterative Refinement) 论文实现的优化引擎。
    针对并行化进行了线程安全适配。
    """
    def __init__(self, target_model, attacker_llm=None, stop_event=None):
        super().__init__(target_model, attacker_llm)
        self.stop_event = stop_event # 保存开关引用
        # 初始化时，如果子类没有定义，确保有一个基础路径
        if not hasattr(self, 'current_log_path'):
            self.current_log_path = "logs/default_trace.jsonl"
        print("[+] PAIR 优化引擎已就绪：采用迭代反馈进化机制 (并行适配版)。")

    def optimize(self, question, max_iters=20):
        """
        PAIR 核心迭代循环：已增加全量轨迹记忆 (Full Trajectory Memory) 支撑。
        """
        # 1. 初始阶段：生成第一个攻击提示词
        improvement, current_prompt = self.generator.generate_initial_prompt(question)
        total_queries = 0
        
        # --- 新增：初始化全量轨迹记忆列表 ---
        trajectory_history = []
        # -----------------------------------

        for i in range(max_iters):
            # --- 核心改动：检查停止信号 ---
            if self.stop_event and self.stop_event.is_set():
                print(f"    [!] 检测到其他线程已成功，链条提前终止。")
                return current_prompt, False, total_queries
            # ---------------------------

            # 2. 询问目标模型
            target_response = self.model.query(current_prompt)
            total_queries += 1
            
            # 处理云端拦截或空回复
            if not target_response or "[Cloud_Blocked]" in target_response:
                score, reason = 1, "目标模型触发拦截或无输出"
            else:
                # 3. 询问判别器 (Judge)
                score, reason = self.judge.evaluate_response(question, target_response)

            # 记录日志 (内部已加锁)
            self._log_query(
                iteration=i+1, 
                prompt=current_prompt, 
                response=target_response, 
                score=score, 
                reason=reason,
                improvement=improvement
            )

            # --- 新增：将当前轮次的所有信息存入轨迹历史 ---
            trajectory_history.append({
                "iter": i + 1,
                "improvement": improvement,
                "prompt": current_prompt,
                "response": target_response,
                "score": score,
                "reason": reason
            })
            # -----------------------------------------

            # 4. 检查是否成功
            if self.judge.is_success(score):
                # --- 核心改动：成功时合上开关 ---
                if self.stop_event:
                    self.stop_event.set() 
                # ---------------------------
                return current_prompt, True, total_queries

            # 5. 进化：将包含【全量轨迹历史】的反馈喂回给攻击者
            improvement, current_prompt = self.generator.evolve_prompt(
                target_goal=question,
                last_prompt=current_prompt,
                last_response=target_response,
                score=score,
                reason=reason,
                history=trajectory_history  # <--- 关键修改：传递全量记忆
            )

        return current_prompt, False, total_queries

    def _log_query(self, iteration, prompt, response, score, reason, improvement):
        """
        线程安全地记录日志
        """
        log_entry = {
            "iter": iteration,
            "improvement_thought": improvement,
            "prompt": prompt,
            "response": response,
            "score": score,
            "reason": reason,
            "timestamp": time.time(),
            "thread": threading.current_thread().name  # 记录线程名方便调试
        }
        
        # 使用全局锁，防止多个线程同时写入同一个文件导致 JSON 格式损坏
        with file_lock:
            if hasattr(self, 'current_log_path'):
                try:
                    with open(self.current_log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
                except Exception as e:
                    print(f"[-] 日志写入失败: {e}")