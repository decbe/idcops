#!/usr/bin/env python3
"""生成一个 54 字符的随机密钥，适合用作 Django SECRET_KEY。

使用方法:
    python generate_secret_key.py

然后将输出添加到 .env 文件中:
    SECRET_KEY=<生成的密钥>
"""
import secrets

charset = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*(-_=+)"
print("".join(secrets.choice(charset) for _ in range(54)))
