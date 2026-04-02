import torch
import os
import time
import random
import threading  # 新增：用于并发控制
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from dotenv import load_dotenv

# 严格遵循你提供的官方文档引入方式
try:
    from zai import ZhipuAiClient
except ImportError:
    print("[-] 错误：未检测到 zai SDK，请确保已安装该特定版本。")

load_dotenv()

# 全局并发控制：根据智谱 API 的 RPM 限制，建议同时活跃的请求不超过 10-20 个
# 这能有效防止因请求过快导致的批量 429 错误
max_concurrent_requests = threading.Semaphore(15)

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
# 2. CloudModel (适配并行化与重试逻辑)
# ==========================================
class CloudModel:
    def __init__(self, api_key_env="ZHIPU_API_KEY", role="Attacker"):
        self.api_key = os.getenv(api_key_env)
        self.role = role
        
        if not self.api_key:
            print(f"[!] 警告：未在 .env 中找到 {api_key_env}")
        
        print(f"[*] 初始化智谱云端实例 [{self.role}]...")
        
        try:
            self.client = ZhipuAiClient(api_key=self.api_key)
        except Exception as e:
            self.client = None
            print(f"[-] 错误：{self.role} 客户端初始化失败: {e}")
            
        self.model_name = "glm-4-flash" 
        self.lock = threading.Lock() # 新增本地模型锁

    def query(self, prompt, system_prompt=None, temperature=0.6, max_retries=3):
        with self.lock:
            if not self.client:
                return "[Cloud_Error] 客户端未就绪"

            # 使用 Semaphore 控制并发，防止瞬时请求压垮 API
            with max_concurrent_requests:
                for attempt in range(max_retries):
                    try:
                        messages = []
                        if system_prompt:
                            messages.append({"role": "system", "content": system_prompt})
                        messages.append({"role": "user", "content": prompt})

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
                        
                        # 如果是频率限制 (Rate Limit) 或者是网络波动，执行退避重试
                        if any(k in err_msg for k in ["429", "rate limit", "timeout", "connection"]):
                            wait_time = (2 ** attempt) + random.random()
                            print(f"  [!] {self.role} 触发频率限制，{wait_time:.1f}s 后进行第 {attempt+1} 次重试...")
                            time.sleep(wait_time)
                            continue
                        
                        # 如果是安全策略拦截，直接返回，不重试
                        if any(k in err_msg for k in ["policy", "sensitive", "1301"]):
                            return "[Cloud_Blocked] 触发 API 侧安全过滤"
                        
                        return f"[Cloud_Error] {err_msg}"
                
                return "[Cloud_Error] 超过最大重试次数"


# ==========================================
# 3. 角色工厂函数 (保持原样)
# ==========================================
def get_attacker_model():
    return CloudModel(api_key_env="ZHIPU_API_KEY", role="Attacker")

def get_judge_model():
    return CloudModel(api_key_env="ZHIPU_JUDGE_API_KEY", role="Judge")

def get_target_model():
    """选择被攻击的目标模型 (支持本地或专用云端 Key)"""
    print("\n" + "="*40)
    print("      请选择被攻击的目标模型 (Target LLM)")
    print("="*40)
    print(" [1] 本地 Qwen2.5-3B")
    print(" [2] 云端 GLM-4-Flash (使用专用 Target Key)")
    print("="*40)
    
    choice = input("\n请输入选项 (默认 1): ").strip()
    
    if choice == "2":
        # 核心改动：这里传入你 .env 中新定义的变量名
        return CloudModel(api_key_env="ZHIPU_TARGET_API_KEY", role="Target")
    else:
        return LocalModel()