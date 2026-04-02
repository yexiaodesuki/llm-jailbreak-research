import time
import json
import os
from src.generator.prompt_generator import PromptGenerator
from src.judge.judge import Judge

class QueryOpt:
    def __init__(self, target_model, attacker_llm=None):
        """
        初始化优化器
        :param target_model: 接收攻击的目标模型 (通常是 LocalModel)
        :param attacker_llm: 负责生成/进化提示词的攻击者模型 (通常是 CloudModel)
        """
        self.model = target_model
        
        # --- [关键修改点] ---
        # 如果提供了专门的攻击者 LLM，则使用它；否则回退到使用目标模型（保持向后兼容）
        generator_llm = attacker_llm if attacker_llm is not None else target_model
        
        self.generator = PromptGenerator(llm_engine=generator_llm) 
        self.judge = Judge()
        self.current_log_path = None
        
        # 判定目标模型是否为云端（用于处理硬拦截逻辑）
        self.is_cloud = "CloudModel" in str(type(target_model))

    def optimize(self, question, max_iters=3, beam_width=3):
        """
        反馈驱动的进化优化器
        节点 A: 初始冷启动变异
        节点 B: 基于精英提示词的语义进化
        """
        queried_prompts = set()
        total_queries = 0

        def perform_query(p):
            try:
                # 始终向目标模型（target_model）发起请求
                res = self.model.query(p)
                if self.is_cloud and (not res or len(res.strip()) < 5):
                    return "[Cloud_Blocked] 检测到云端硬拦截，该路径已封锁。", 0.0
                score = self.judge.get_score(res, question)
                return res, score
            except Exception as e:
                return f"[Error] 接口请求异常: {str(e)}", 0.0

        # --- 第一阶段：基准探测 (Baseline) ---
        raw_res, raw_score = perform_query(question)
        total_queries += 1
        queried_prompts.add(question)
        self._log_query("Baseline", question, raw_res, raw_score, strategy="原始指令", q_count=1)

        if self.judge.is_success(raw_score):
            return question, True, total_queries

        # --- 第二阶段：节点 A - 开局初始化 (P0) ---
        print(f"[*] 触发节点 A: 基于攻击者 LLM 进行开局多样化变异...")
        initial_variants, initial_strategies = self.generator.generate_initial_seeds(question, k=beam_width)
        
        beam_pool = []
        for idx, p in enumerate(initial_variants):
            res, score = perform_query(p)
            total_queries += 1
            queried_prompts.add(p)
            strat = initial_strategies[idx] if idx < len(initial_strategies) else "Initial_Gen"
            self._log_query("P0_Init", p, res, score, strategy=strat, q_count=1)
            
            beam_pool.append((p, score, res))
            if self.judge.is_success(score):
                return p, True, total_queries

        # --- 第三阶段：节点 B - 启发式进化迭代 (Iterative Evolution) ---
        best_overall_prompt = question
        best_overall_score = raw_score

        for i in range(max_iters):
            # 排序获取当前最优（Elite）
            beam_pool.sort(key=lambda x: x[1], reverse=True)
            elite_prompt, elite_score, _ = beam_pool[0]
            
            if elite_score > best_overall_score:
                best_overall_score = elite_score
                best_overall_prompt = elite_prompt

            print(f"\n>>> 演化轮次 {i+1}/{max_iters} | 当前最优分: {elite_score:.3f}")
            print(f"[*] 触发节点 B: 基于精英提示词进行‘语义进化’...")

            # 进化逻辑：由 generator (即 attacker_llm) 完成
            new_variants, new_strategies = self.generator.evolve_variants(
                elite_prompt=elite_prompt,
                elite_score=elite_score,
                original_query=question,
                k=beam_width
            )

            new_candidates_pool = []
            for idx, v_prompt in enumerate(new_variants):
                if v_prompt in queried_prompts:
                    continue
                
                response, score = perform_query(v_prompt)
                queried_prompts.add(v_prompt)
                total_queries += 1
                
                strat_name = new_strategies[idx] if idx < len(new_strategies) else "Evolution"
                self._log_query(f"Iter {i+1}", v_prompt, response, score, strategy=strat_name, q_count=1)
                
                new_candidates_pool.append((v_prompt, score, response))
                
                if self.judge.is_success(score):
                    print(f"\n[!] 进化成功！总查询数: {total_queries}")
                    return v_prompt, True, total_queries

            # 如果本轮没有产生任何新结果，尝试使用 Fallback 逻辑
            if not new_candidates_pool:
                print("[!] 进化未产生新变体，切换至随机 Fallback...")
                fallback_variants, fallback_strats = self.generator._generate_fallback(question, k=1)
                for f_p, f_s in zip(fallback_variants, fallback_strats):
                    res, sc = perform_query(f_p)
                    new_candidates_pool.append((f_p, sc, res))

            # 更新精英池（存活竞争）
            combined_pool = beam_pool + new_candidates_pool
            combined_pool.sort(key=lambda x: x[1], reverse=True)
            beam_pool = combined_pool[:beam_width]

        return best_overall_prompt, False, total_queries

    def _log_query(self, stage_name, prompt, response, score, strategy=None, q_count=1):
        """标准化实验日志输出"""
        is_blocked = "[Cloud_Blocked]" in response
        res_preview = " ".join(response.split())[:120]
        
        print(f"  [{stage_name}] Score: {score:.3f} | {strategy}")
        if is_blocked:
            print(f"  [Res] \033[91m{res_preview}\033[0m") 
        else:
            print(f"  [Res] {res_preview}...")

        if self.current_log_path:
            log_entry = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "stage": stage_name,
                "strategy": strategy if strategy else "未知",
                "score": round(score, 3),
                "queries_used": q_count,
                "prompt": prompt,
                "response": response
            }
            try:
                os.makedirs(os.path.dirname(self.current_log_path), exist_ok=True)
                with open(self.current_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            except Exception as e:
                print(f"[-] 日志 IO 异常: {e}")