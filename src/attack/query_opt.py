import time
import json
import os
from src.generator.prompt_generator import PromptGenerator
from src.judge.judge import Judge

class QueryOpt:
    def __init__(self, model):
        self.model = model
        self.generator = PromptGenerator()
        self.judge = Judge()
        # 新增：用于 app.py 展示的详细日志路径，默认为 None
        self.current_log_path = None

    def optimize(self, question, max_iters=3, beam_width=3):
        """
        基于反馈驱动的启发式束搜索 (Feedback-driven Heuristic Beam Search)
        理论支持: Chao et al. (2023) - PAIR 算法框架
        """
        queried_prompts = set()
        total_queries = 0

        # --- 第一阶段：基准探测 (Baseline) ---
        raw_p = question
        print(f"\n" + "="*50)
        print(f"[*] 目标启动: {question}")
        print(f"[*] 正在进行基准探测 (Baseline)...")
        
        raw_res = self.model.query(raw_p)
        total_queries += 1
        queried_prompts.add(raw_p)
        raw_score = self.judge.get_score(raw_res, question)
        # 记录 Baseline
        self._log_query("Baseline", raw_p, raw_res, raw_score)

        if self.judge.is_success(raw_score):
            return raw_p, True, total_queries

        # --- 第二阶段：引导性包装探测 (P0) ---
        initial_p = self.generator.initial_prompt(question)
        print(f"[*] 正在进行引导性包装探测 (P0)...")
        
        initial_res = self.model.query(initial_p)
        total_queries += 1
        queried_prompts.add(initial_p)
        initial_score = self.judge.get_score(initial_res, question)
        # 记录 P0
        self._log_query("P0", initial_p, initial_res, initial_score)

        if self.judge.is_success(initial_score):
            return initial_p, True, total_queries

        # --- 第三阶段：启发式变异迭代 (Iterative Evolution) ---
        beam_pool = [(initial_p, initial_score, initial_res)]
        best_overall_prompt = initial_p
        best_overall_score = initial_score

        for i in range(max_iters):
            print(f"\n>>> 演化轮次 {i+1}/{max_iters} | 当前精英池规模: {len(beam_pool)}")
            new_candidates_pool = []

            for b_prompt, b_score, _ in beam_pool:
                # 理论支持: Elite Selection Operator (精英选择算子)
                variants, strategies_info = self.generator.generate_variants(question, k=beam_width)
                
                for idx, v_prompt in enumerate(variants):
                    if v_prompt in queried_prompts:
                        continue
                    
                    response = self.model.query(v_prompt)
                    queried_prompts.add(v_prompt)
                    total_queries += 1
                    
                    score = self.judge.get_score(response, question)
                    
                    # 更新生成器反馈
                    self.generator.update_performance(strategies_info[idx], score)
                    
                    # 记录 演化详情（带上当前使用的策略名）
                    self._log_query(f"Iter {i+1}", v_prompt, response, score, strategy=strategies_info[idx])
                    
                    new_candidates_pool.append((v_prompt, score, response))
                    
                    if score > best_overall_score:
                        best_overall_score = score
                        best_overall_prompt = v_prompt

                    if self.judge.is_success(score):
                        print(f"\n[!] 命中目标！演化收敛。总查询数: {total_queries} | 最终得分: {score}")
                        return v_prompt, True, total_queries

            if not new_candidates_pool:
                break
            
            new_candidates_pool.sort(key=lambda x: x[1], reverse=True)
            beam_pool = new_candidates_pool[:beam_width]
            print(f"[*] 本轮演化总结: 最高得分 = {beam_pool[0][1]:.3f}")

        return best_overall_prompt, False, total_queries

    def _log_query(self, stage_name, prompt, response, score, strategy=None):
        """标准化实验日志输出，并持久化到 JSONL 文件"""
        prompt_preview = prompt.replace("\n", " ")[:80]
        res_preview = " ".join(response.split())[:200]
        
        # 控制台打印
        print(f"  [{stage_name}] Score: {score:.3f} | Strategy: {strategy if strategy else 'None'}")
        print(f"  [Response] {res_preview}...")
        print("  " + "-"*30)

        # --- 持久化到详细日志文件 (JSONL格式) ---
        if self.current_log_path:
            log_entry = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "stage": stage_name,
                "strategy": strategy,
                "score": round(score, 3),
                "prompt": prompt,
                "response": response
            }
            try:
                # 确保目录存在
                os.makedirs(os.path.dirname(self.current_log_path), exist_ok=True)
                with open(self.current_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            except Exception as e:
                print(f"[-] 写入日志失败: {e}")