import os
from dotenv import load_dotenv
from model_api import get_attacker_model, get_judge_model

def test_models():
    load_dotenv()
    
    print("\n" + "="*50)
    print("      智谱 AI SDK (zai) 调用测试")
    print("="*50)

    # 1. 测试攻击者模型 (使用原有的 ZHIPU_API_KEY)
    print("\n[测试 1] 正在尝试初始化 Attacker (主 Key)...")
    try:
        attacker = get_attacker_model()
        # 简单问个好，不涉及敏感话题，确认链路通畅
        res = attacker.query("你好，这是一条来自自动化红队系统的测试指令。请回复：Attacker 就绪。")
        print(f"[Result] Attacker 回复: {res}")
    except Exception as e:
        print(f"[!] Attacker 调用发生程序崩溃: {e}")

    print("\n" + "-"*50)

    # 2. 测试评估者模型 (使用预留的 ZHIPU_JUDGE_API_KEY)
    print("[测试 2] 正在尝试初始化 Judge (新 Key)...")
    # 如果你还没填 Key，这里应该打印警告并返回 Cloud_Error
    judge_key = os.getenv("ZHIPU_JUDGE_API_KEY")
    if not judge_key:
        print("[预期结果] 检测到 ZHIPU_JUDGE_API_KEY 为空，符合预期（你尚未填充）。")
    
    try:
        judge = get_judge_model()
        res = judge.query("你好，请回复：Judge 就绪。")
        print(f"[Result] Judge 回复: {res}")
    except Exception as e:
        print(f"[!] Judge 调用发生错误（如果是 Key 缺失，这是正常的）: {e}")

    print("\n" + "="*50)
    print("测试完成。")

if __name__ == "__main__":
    test_models()