import torch
import os
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

class LocalModel:
    def __init__(self, model_name=None):
        # 1. 使用 Path 对象规范化路径
        if model_name is None:
            # 确保这里指向包含 config.json 的 snapshots 具体哈希文件夹
            raw_path = r"D:\huggingface_cache\hub\models--Qwen--Qwen2.5-3B-Instruct\snapshots\aa8e72537993ba99e69dfaafa59ed015b17504d1"
            self.model_path = Path(raw_path)
        else:
            self.model_path = Path(model_name)

        # 检查路径是否存在，避免盲目加载
        if not self.model_path.exists():
            raise FileNotFoundError(f"[-] 错误：找不到模型目录: {self.model_path}")

        # 将路径转换为字符串格式，确保使用正斜杠（部分库版本对反斜杠敏感）
        self.model_str = str(self.model_path.absolute()).replace("\\", "/")

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        )

        print(f"[*] 正在离线加载本地模型: {self.model_str}")

        try:
            # 2. 加载 Tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_str,
                trust_remote_code=True,
                local_files_only=True 
            )

            # 3. 加载 Model
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_str,
                quantization_config=bnb_config,
                device_map="auto",
                trust_remote_code=True,
                local_files_only=True 
            )
            self.model.eval()
            print("[+] 模型加载成功 (Offline Mode)")
        except Exception as e:
            # 如果依然报错 Repo ID，尝试在路径前加一个特殊标记或确保它是绝对路径
            print(f"[-] 加载失败: {e}")
            raise e

    def generate(self, prompt, max_new_tokens=200):
        # 这里的逻辑保持不变
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=True,
                temperature=0.8,
                top_p=0.95,
                top_k=50,
                repetition_penalty=1.1,
            )
        return self.tokenizer.decode(outputs[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True)

    def query(self, prompt):
        return self.generate(prompt)