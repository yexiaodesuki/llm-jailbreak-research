import sys
import os
from src.models.model_api import CloudModel
from src.generator.prompt_generator import PromptGenerator

def run_diagnosis():
    print("=== 启动演化逻辑深度调查 ===")
    
    # 1. 检查环境变量
    api_key = os.getenv("ZHIPU_API_KEY")
    print(f"[1] 环境变量检查: {'已找到 API_KEY' if api_key else '未找到 API_KEY (请检查 .env 文件)'}")

    # 2. 检查模型实例化
    try:
        model = CloudModel()
        print(f"[2] CloudModel 实例化: 成功 (API Key: {model.api_key[:5]}***)")
    except Exception as e:
        print(f"[2] CloudModel 实例化: 失败 - {e}")
        return

    # 3. 检查模型查询方法
    print(f"[3] 模型方法探测: ")
    available_methods = [m for m in dir(model) if not m.startswith("__")]
    print(f"    可用方法: {available_methods}")
    
    test_method = "query" if hasattr(model, "query") else "get_response"
    print(f"    决策: 建议调用的查询方法为 '{test_method}'")

    # 4. 模拟 Generator 调用
    print(f"[4] 模拟策略生成测试...")
    
    # 修复点：在构造时直接传入模型，或者确保变量名一致
    generator = PromptGenerator(llm_engine=model) 
    
    # 手动触发测试，带上详细的报错捕获
    test_prompt = "请生成 1 个关于系统漏洞分析的变体。"
    try:
        # 内部调用 _call_llm_for_json
        print(f"    正在发送请求至模型...")
        res = generator._call_llm_for_json(test_prompt)
        
        if res:
            print(f"    结果: 成功生成动态策略! -> {res}")
        else:
            print(f"    结果: 返回为空。")
            print(f"    可能原因：1. 模型拒绝回答敏感词 2. JSON 格式没对上 3. self.llm 依然为 None")
            print(f"    当前 Generator 内部 llm 状态: {'已绑定' if generator.llm else '未绑定(None)'}")
            
    except Exception as e:
        print(f"    结果: 调用崩溃 - {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_diagnosis()