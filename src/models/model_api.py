import torch
import os
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from dotenv import load_dotenv

# 严格遵循你提供的官方文档引入方式
try:
    from zai import ZhipuAiClient
except ImportError:
    print("[-] 错误：未检测到 zai SDK，请确保已安装该特定版本。")

load_dotenv()

# ==========================================
# 1. LocalModel (保持原样，适配 Qwen2.5)
# ==========================================
class LocalModel:
    def __init__(self, model_name=None):
        raw_path = r"D:\huggingface_cache\hub\models--Qwen--Qwen2.5-3B-Instruct\snapshots\aa8e72537993ba99e69dfaafa59ed015b17504d1"
        self.model_path = Path(raw_path)
        self.model_str = str(self.model_path.absolute()).replace("\\", "/")

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        )

        print(f"[*] 正在加载本地目标模型: {self.model_str}")
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_str, trust_remote_code=True, local_files_only=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_str, 
            quantization_config=bnb_config, 
            device_map="auto", 
            trust_remote_code=True, 
            local_files_only=True
        )
        self.model.eval()

    def query(self, prompt, system_prompt=None):
        # 简单拼接以适配本地模型对话格式
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        inputs = self.tokenizer(full_prompt, return_tensors="pt").to(self.model.device)
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs, 
                max_new_tokens=512, 
                do_sample=True, 
                temperature=0.7, 
                top_p=0.9
            )
        return self.tokenizer.decode(outputs[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True)


# ==========================================
# 2. CloudModel (适配 zai SDK 并支持多实例)
# ==========================================
class CloudModel:
    def __init__(self, api_key_env="ZHIPU_API_KEY", role="Attacker"):
        """
        api_key_env: 环境变量名
        role: 角色说明 (Attacker / Judge)
        """
        self.api_key = os.getenv(api_key_env)
        self.role = role
        
        if not self.api_key:
            print(f"[!] 警告：未在 .env 中找到 {api_key_env}")
        
        print(f"[*] 初始化智谱云端实例 [{self.role}]...")
        
        try:
            # 使用官方文档提供的初始化方式
            self.client = ZhipuAiClient(api_key=self.api_key)
        except Exception as e:
            self.client = None
            print(f"[-] 错误：{self.role} 客户端初始化失败: {e}")
            
        # 默认使用 glm-4-flash (经济高效)，如果需要 glm-5 请在此修改
        self.model_name = "glm-4-flash" 

    def query(self, prompt, system_prompt=None, temperature=0.6):
        if not self.client:
            return "[Cloud_Error] 客户端未就绪"

        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            # 严格遵循官方文档的调用路径
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temperature
            )
            
            res_text = response.choices[0].message.content

            # 拦截识别逻辑
            if not res_text or len(res_text.strip()) < 5:
                return "[Cloud_Blocked] 安全网关实时拦截"
            
            refusal_patterns = ["无法提供帮助", "违反安全策略", "不合规", "抱歉"]
            if any(p in res_text for p in refusal_patterns):
                return f"[Cloud_Blocked] 触发模型内置防御"

            return res_text

        except Exception as e:
            err_msg = str(e).lower()
            if any(k in err_msg for k in ["policy", "sensitive", "1301"]):
                return "[Cloud_Blocked] 触发 API 侧安全过滤"
            return f"[Cloud_Error] {err_msg}"


# ==========================================
# 3. 角色工厂函数
# ==========================================

def get_attacker_model():
    """获取攻击者实例（使用默认 Key）"""
    return CloudModel(api_key_env="ZHIPU_API_KEY", role="Attacker")

def get_judge_model():
    """获取评估者实例（使用新的专用 Key）"""
    return CloudModel(api_key_env="ZHIPU_JUDGE_API_KEY", role="Judge")

def get_target_model():
    """选择被攻击的目标模型"""
    print("\n" + "="*40)
    print("      请选择被攻击的目标模型 (Target LLM)")
    print("="*40)
    print(" [1] 本地 Qwen2.5-3B")
    print(" [2] 云端 GLM-4-Flash")
    print("="*40)
    choice = input("\n请输入选项 (默认 1): ").strip()
    return CloudModel(role="Target") if choice == "2" else LocalModel()