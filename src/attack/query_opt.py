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
        # 用于 app.py 展示的详细日志路径
        self.current_log_path = None
        
        # --- [逻辑点 1：识别模型身份] ---
        # 判定标准：CloudModel 类名或你在 model_api.py 中定义的标签
        self.is_cloud = "CloudModel" in str(type(model))

    def optimize(self, question, max_iters=3, beam_width=3):
        """
        基于反馈驱动的启发式束搜索 (App 对齐版)
        """
        queried_prompts = set()
        total_queries = 0

        # --- [新增辅助函数：处理查询与硬拦截] ---
        def perform_query(p):
            try:
                res = self.model.query(p)
                # 如果是云端模型且返回为空/极短，判定为网关硬拦截
                if self.is_cloud and (not res or len(res.strip()) < 5):
                    return "[Cloud_Blocked] 检测到云端硬拦截，该路径已封锁。", 0.0
                
                score = self.judge.get_score(res, question)
                return res, score
            except Exception as e:
                # 针对网络超时或 API 错误返回特定格式
                return f"[Cloud_Error] 接口请求异常: {str(e)}", 0.0

        # --- 第一阶段：基准探测 (Baseline) ---
        raw_p = question
        print(f"\n" + "="*50)
        print(f"[*] 目标启动: {question[:30]}... | 环境: {'☁️ Cloud' if self.is_cloud else '🏠 Local'}")
        
        raw_res, raw_score = perform_query(raw_p)
        total_queries += 1
        queried_prompts.add(raw_p)
        
        # 适配 App：传递查询计数
        self._log_query("Baseline", raw_p, raw_res, raw_score, strategy="原始指令", q_count=1)
        
        if self.judge.is_success(raw_score):
            return raw_p, True, total_queries

        # --- 第二阶段：引导性包装探测 (P0) ---
        initial_p = self.generator.initial_prompt(question, use_obfuscation=self.is_cloud)
        
        initial_res, initial_score = perform_query(initial_p)
        total_queries += 1
        queried_prompts.add(initial_p)
        
        self._log_query("P0", initial_p, initial_res, initial_score, strategy="引导性包装", q_count=1)
        
        if self.judge.is_success(initial_score):
            return initial_p, True, total_queries

        # --- 第三阶段：启发式变异迭代 (Iterative Evolution) ---
        beam_pool = [(initial_p, initial_score, initial_res)]
        best_overall_prompt = initial_p
        best_overall_score = initial_score

        for i in range(max_iters):
            print(f"\n>>> 演化轮次 {i+1}/{max_iters} | 精英池: {len(beam_pool)}")
            new_candidates_pool = []

            for b_prompt, b_score, _ in beam_pool:
                # 生成变体
                variants, strategies_info = self.generator.generate_variants(
                    question, 
                    k=beam_width, 
                    use_obfuscation=self.is_cloud
                )
                
                for idx, v_prompt in enumerate(variants):
                    if v_prompt in queried_prompts:
                        continue
                    
                    response, score = perform_query(v_prompt)
                    queried_prompts.add(v_prompt)
                    total_queries += 1
                    
                    # 更新反馈
                    strat_name = strategies_info[idx] if idx < len(strategies_info) else "未知策略"
                    self.generator.update_performance(strat_name, score)
                    
                    # 关键记录：写入日志供 App.py 读取
                    self._log_query(f"Iter {i+1}", v_prompt, response, score, strategy=strat_name, q_count=1)
                    
                    new_candidates_pool.append((v_prompt, score, response))
                    
                    if score > best_overall_score:
                        best_overall_score = score
                        best_overall_prompt = v_prompt

                    if self.judge.is_success(score):
                        print(f"\n[!] 命中目标！总查询数: {total_queries}")
                        return v_prompt, True, total_queries

            if not new_candidates_pool:
                break
            
            new_candidates_pool.sort(key=lambda x: x[1], reverse=True)
            beam_pool = new_candidates_pool[:beam_width]

        return best_overall_prompt, False, total_queries

    def _log_query(self, stage_name, prompt, response, score, strategy=None, q_count=1):
        """标准化实验日志输出，支持 App.py 实时查询计数"""
        is_blocked = "[Cloud_Blocked]" in response
        res_preview = " ".join(response.split())[:120]
        
        # 控制台美化打印
        print(f"  [{stage_name}] Score: {score:.3f} | {strategy}")
        if is_blocked:
            print(f"  [Res] \033[91m{res_preview}\033[0m") 
        else:
            print(f"  [Res] {res_preview}...")

        # 写入 JSONL (供 App.py 回放)
        if self.current_log_path:
            log_entry = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "stage": stage_name,
                "strategy": strategy if strategy else "未知",
                "score": round(score, 3),
                "queries_used": q_count,  # 每一行记录本次操作消耗的查询数
                "prompt": prompt,
                "response": response
            }
            try:
                os.makedirs(os.path.dirname(self.current_log_path), exist_ok=True)
                with open(self.current_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            except Exception as e:
                print(f"[-] 日志 IO 异常: {e}")