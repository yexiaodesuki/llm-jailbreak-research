import time
import json
from src.attack.query_opt import QueryOpt

class ImprovedQueryOpt(QueryOpt):
    """
    完全参照 PAIR (Prompt Automatic Iterative Refinement) 论文实现的优化引擎。
    """
    def __init__(self, target_model, attacker_llm=None):
        super().__init__(target_model, attacker_llm)
        print("[+] PAIR 优化引擎已就绪：采用迭代反馈进化机制。")

    def optimize(self, question, max_iters=20):
        """
        PAIR 核心迭代循环
        """
        # 1. 初始阶段：生成第一个攻击提示词
        # 调用我们改好的 prompt_generator.py 中的接口
        improvement, current_prompt = self.generator.generate_initial_prompt(question)
        
        # 记录该攻击链的历史 (用于给 Attacker 提供上下文)
        history = []
        total_queries = 0

        for i in range(max_iters):
            print(f"\n>>> [迭代轮次 {i+1}/{max_iters}]")
            
            # 2. 询问目标模型 (本地 Qwen)
            target_response = self.model.query(current_prompt)
            total_queries += 1
            
            # 处理云端拦截或空回复
            if not target_response or "[Cloud_Blocked]" in target_response:
                score, reason = 1, "目标模型触发拦截或无输出"
            else:
                # 3. 询问判别器 (Judge)
                score, reason = self.judge.evaluate_response(question, target_response)

            # 记录日志
            self._log_query(
                iteration=i+1, 
                prompt=current_prompt, 
                response=target_response, 
                score=score, 
                reason=reason,
                improvement=improvement
            )

            # 4. 检查是否成功 (Score >= 10 或你在 judge 设定的阈值)
            if self.judge.is_success(score):
                print(f"[!] 越狱成功！得分: {score}")
                return current_prompt, True, total_queries

            # 5. 进化：将反馈喂回给攻击者生成下一个提示词
            print(f"[*] 当前得分: {score}，正在根据理由改进...")
            improvement, current_prompt = self.generator.evolve_prompt(
                target_goal=question,
                last_prompt=current_prompt,
                last_response=target_response,
                score=score,
                reason=reason
            )

        return current_prompt, False, total_queries

    def _log_query(self, iteration, prompt, response, score, reason, improvement):
        """
        按照你的 run_research_eval.py 需要的格式记录日志
        """
        log_entry = {
            "iter": iteration,
            "improvement_thought": improvement,
            "prompt": prompt,
            "response": response,
            "score": score,
            "reason": reason,
            "timestamp": time.time()
        }
        # 这里会将日志写入到你在 run_research_eval.py 中指定的 trace 文件
        if hasattr(self, 'current_log_path'):
            with open(self.current_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")