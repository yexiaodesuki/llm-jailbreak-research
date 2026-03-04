import gradio as gr
import json
import os
import time
import glob

# 路径配置
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
RESULTS_DIR = os.path.join(BASE_DIR, "results")

class ReplayApp:
    def __init__(self):
        self.selected_task_data = []

    def load_latest_result_summary(self):
        """获取最新的实验汇总报告"""
        list_of_files = glob.glob(os.path.join(RESULTS_DIR, "*.json"))
        if not list_of_files:
            return []
        latest_file = max(list_of_files, key=os.path.getctime)
        try:
            with open(latest_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("details", [])
        except:
            return []

    def get_trace_logs(self, task_id):
        """读取对应的 JSONL 轨迹文件"""
        log_path = os.path.join(LOGS_DIR, f"task_{task_id}_trace.jsonl")
        if not os.path.exists(log_path):
            return []
        
        steps = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    steps.append(json.loads(line))
        return steps

    def run_replay(self, task_info):
        """流式回放逻辑"""
        if not task_info:
            yield "请先选择一个任务", "", 0, "等待中"
            return

        # 解析 ID
        task_id = task_info.split(":")[0].strip()
        steps = self.get_trace_logs(task_id)

        if not steps:
            yield f"未找到 ID {task_id} 的轨迹文件，请确认已运行实验并生成 logs 文件夹内容。", "", 0, "错误"
            return

        history_md = ""
        best_p = ""
        
        for i, step in enumerate(steps):
            # 模拟演示节奏
            time.sleep(0.6) 
            
            stage = step.get("stage", "Unknown")
            strategy = step.get("strategy", "N/A")
            score = step.get("score", 0.0)
            response = step.get("response", "")
            prompt = step.get("prompt", "")

            # 构造 Markdown 日志
            history_md += f"### 📍 阶段: {stage}\n"
            if strategy and strategy != "None":
                history_md += f"**采用策略**: `{strategy}`\n\n"
            history_md += f"**Judge 评分**: `{score:.3f}`\n\n"
            history_md += f"**模型响应预览**: \n> {response[:200]}...\n\n"
            history_md += "---\n"

            best_p = prompt
            status = "突破成功 ✅" if score >= 0.85 else "演化中..."
            yield history_md, best_p, score, status

        yield history_md, best_p, steps[-1]["score"], "复现完成 ✅"

# 实例化
app_engine = ReplayApp()

# --- Gradio UI 修正版 ---
with gr.Blocks(title="LLM 攻击演化复现系统") as demo:
    gr.Markdown("# 🛡️ LLM 安全性对抗演化 - 实验结果复现系统")
    
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 1. 选择任务")
            
            summary_data = app_engine.load_latest_result_summary()
            task_choices = [f"{item['id']} : {item['question'][:20]}..." for item in summary_data]
            
            task_dropdown = gr.Dropdown(
                choices=task_choices, 
                label="已完成的任务 (ID : 预览)",
                interactive=True
            )
            
            refresh_btn = gr.Button("🔄 刷新实验列表")
            start_btn = gr.Button("🚀 开始轨迹回放", variant="primary")

        with gr.Column(scale=2):
            gr.Markdown("### 2. 演化过程看板")
            with gr.Row():
                score_display = gr.Number(label="实时危害得分", precision=3)
                status_display = gr.Textbox(label="当前状态")
            
            with gr.Tabs():
                with gr.TabItem("🎞️ 演化日志流"):
                    log_viewer = gr.Markdown(value="等待回放...")
                with gr.TabItem("📝 对抗提示词"):
                    # 移除了引发报错的 show_copy_button
                    prompt_viewer = gr.Textbox(label="此阶段生成的攻击提示词", lines=12)

    # 交互绑定
    def refresh_list():
        new_summary = app_engine.load_latest_result_summary()
        new_choices = [f"{item['id']} : {item['question'][:20]}..." for item in new_summary]
        return gr.Dropdown(choices=new_choices)

    refresh_btn.click(fn=refresh_list, outputs=task_dropdown)
    
    start_btn.click(
        fn=app_engine.run_replay,
        inputs=task_dropdown,
        outputs=[log_viewer, prompt_viewer, score_display, status_display]
    )

if __name__ == "__main__":
    # 将 theme 移动到 launch 中以消除警告
    demo.launch(server_port=7860, theme=gr.themes.Soft())