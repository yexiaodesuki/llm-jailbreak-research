import gradio as gr
import json
import os
import time
import glob
import pandas as pd
import re

# 路径配置
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
RESULTS_DIR = os.path.join(BASE_DIR, "results")

class ReplayApp:
    def __init__(self):
        self.current_env = "local"

    def load_result_summary(self, env):
        """加载实验结果汇总并计算统计指标"""
        target_dir = os.path.join(RESULTS_DIR, env.lower())
        
        # 1. 尝试寻找汇总 JSON 文件
        list_of_files = glob.glob(os.path.join(target_dir, "*.json"))
        
        details = []
        stats = {"levels": {}, "avg_q": 0, "total_asr": 0}

        if list_of_files:
            latest_file = max(list_of_files, key=os.path.getmtime)
            try:
                with open(latest_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    details = data if isinstance(data, list) else data.get("details", [])
                    df = pd.DataFrame(details)
                    if not df.empty:
                        stats["total_asr"] = df['success'].mean() * 100
                        stats["avg_q"] = round(df['queries_used'].mean(), 2) if 'queries_used' in df.columns else 0
                        if 'level' in df.columns:
                            lvl_asr = df.groupby('level')['success'].mean().to_dict()
                            stats["levels"] = {str(k): float(v) * 100 for k, v in lvl_asr.items()}
                return details, stats
            except:
                pass

        # 2. 如果 results 为空，直接从 logs 文件夹反向生成任务列表
        log_dir = os.path.join(LOGS_DIR, env.lower())
        trace_files = glob.glob(os.path.join(log_dir, "task_*_trace.jsonl"))
        
        if trace_files:
            for f_path in trace_files:
                fname = os.path.basename(f_path)
                match = re.search(r'task_(\d+)_trace', fname)
                if match:
                    t_id = match.group(1)
                    details.append({
                        "id": t_id,
                        "level": "Running",
                        "question": f"来自日志的任务 {t_id} (实验中...)"
                    })
            details.sort(key=lambda x: int(x['id']))
            
        return details, stats

    def get_trace_logs(self, task_id, env):
        """读取对应的轨迹日志文件"""
        log_path = os.path.join(LOGS_DIR, env.lower(), f"task_{task_id}_trace.jsonl")
        
        if not os.path.exists(log_path):
            log_path = os.path.join(LOGS_DIR, f"task_{task_id}_trace.jsonl")
        
        if not os.path.exists(log_path):
            return []
        
        steps = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        steps.append(json.loads(line))
                    except:
                        continue
        return steps

    def run_replay(self, task_info, env):
        """流式对抗对话回放"""
        if not task_info:
            yield [], 0, 0, "请先选择一个任务", ""
            return

        task_id = task_info.split(" ")[0].strip()
        steps = self.get_trace_logs(task_id, env)
        
        if not steps:
            yield [{"role": "assistant", "content": "⚠️ 轨迹日志文件尚为空或正在写入中。"}], 0, 0, "ERROR", ""
            return

        chat_history = []
        cum_queries = 0
        
        for i, step in enumerate(steps):
            q_this_step = step.get("queries_used", 1)
            cum_queries += q_this_step
            score = step.get("score", 0.0)
            strategy = step.get("strategy", "待定")
            
            attacker_content = (
                f"🎯 **[演化轮次: Step {i+1}]**\n"
                f"🧠 **攻击策略**: {strategy}\n"
                f"--- \n"
                f"{step.get('prompt', '')}"
            )
            chat_history.append({"role": "user", "content": attacker_content})
            
            yield chat_history, score, cum_queries, f"正在分析第 {i+1} 轮...", step.get("prompt", "")
            time.sleep(0.5)

            raw_res = step.get("response", "").strip()
            score_color = "#2ecc71" if score < 0.5 else ("#f1c40f" if score < 0.8 else "#e74c3c")
            
            # --- 修复渲染 Bug: 强制闭合代码块 ---
            if raw_res.count("```") % 2 != 0:
                raw_res += "\n\n```"
            
            if "[Cloud_Blocked]" in raw_res:
                bot_content = "🚫 **安全网关强力拦截**\n输出已被实时切断。"
            else:
                # 增加三个空行和独立样式的 div 块，防止 Markdown 渲染器将 HTML 吞入上文代码块
                bot_content = (
                    f"{raw_res}\n\n\n"
                    f"<div style='border-top: 1px dashed #ccc; padding-top: 8px; margin-top: 10px; "
                    f"font-size: 0.85em; opacity: 0.9; color: #444; font-family: -apple-system, sans-serif;'>"
                    f"📊 危害评分: <span style='color: {score_color}; font-weight: bold;'>{score:.3f}</span>"
                    f"</div>"
                )
            
            chat_history.append({"role": "assistant", "content": bot_content})
            yield chat_history, score, cum_queries, f"第 {i+1} 轮回放完成", step.get("prompt", "")
            time.sleep(0.3)

# UI 适配 Gradio 6.8.0
css = ".sidebar-panel { background: white; padding: 20px; border-radius: 12px; border: 1px solid #ddd; }"

app_engine = ReplayApp()

with gr.Blocks(theme=gr.themes.Soft(primary_hue="blue"), css=css) as demo:
    gr.HTML("<h1 style='text-align:center;'>🛡️ LLM 安全对抗演化回放系统</h1>")
    
    with gr.Row():
        with gr.Column(scale=1):
            with gr.Column(elem_classes="sidebar-panel"):
                env_radio = gr.Radio(["Local", "Cloud"], label="目标环境", value="Local")
                task_drop = gr.Dropdown(label="已选任务 (ID [梯度] : 问题)")
                with gr.Row():
                    ref_btn = gr.Button("🔄 刷新数据")
                    run_btn = gr.Button("🚀 启动回放", variant="primary")
            
            with gr.Column(elem_classes="sidebar-panel"):
                gr.Markdown("### 📊 全局 ASR 统计 (实验完成后生成)")
                l1_label = gr.Label(label="L1 ASR")
                l2_label = gr.Label(label="L2 ASR")
                l3_label = gr.Label(label="L3 ASR")
                avg_q_num = gr.Number(label="平均查询成本")
            
            with gr.Column(elem_classes="sidebar-panel"):
                cur_score = gr.Number(label="危害评分", precision=3)
                cur_queries = gr.Number(label="累计查询消耗")
                cur_status = gr.Textbox(label="探测状态", interactive=False)

        with gr.Column(scale=2):
            with gr.Tabs():
                with gr.TabItem("💬 对话演化轨迹"):
                    chat_view = gr.Chatbot(height=720)
                with gr.TabItem("📄 核心 Payload 源码"):
                    raw_payload = gr.Textbox(label="当前探测 Prompt", lines=25)

    def sync_ui(env):
        details, stats = app_engine.load_result_summary(env)
        choices = [f"{item.get('id')} [{item.get('level', 'N/A')}] : {item.get('question', '')[:10]}..." for item in details]
        
        l1 = f"{stats.get('levels', {}).get('L1', 0):.1f}%"
        l2 = f"{stats.get('levels', {}).get('L2', 0):.1f}%"
        l3 = f"{stats.get('levels', {}).get('L3', 0):.1f}%"
        
        return gr.Dropdown(choices=choices, value=choices[0] if choices else None), l1, l2, l3, stats.get("avg_q", 0)

    demo.load(fn=lambda: sync_ui("Local"), outputs=[task_drop, l1_label, l2_label, l3_label, avg_q_num])
    env_radio.change(sync_ui, inputs=env_radio, outputs=[task_drop, l1_label, l2_label, l3_label, avg_q_num])
    ref_btn.click(sync_ui, inputs=env_radio, outputs=[task_drop, l1_label, l2_label, l3_label, avg_q_num])
    
    run_btn.click(
        fn=app_engine.run_replay,
        inputs=[task_drop, env_radio],
        outputs=[chat_view, cur_score, cur_queries, cur_status, raw_payload]
    )

if __name__ == "__main__":
    demo.launch(server_port=7860)