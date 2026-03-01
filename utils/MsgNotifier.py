import base64
import hashlib
import hmac
import json
import smtplib
import time
from email.header import Header
from email.mime.text import MIMEText
from typing import Dict

import requests


class Notifier:
    """
    统一推送器
    支持邮件、飞书等多种推送方式
    """

    def __init__(self, config: Dict):
        """
        初始化推送器

        Args:
            config: 推送配置字典；若为 None（如配置未加载），则按空配置处理，不启用任何推送。
        """
        self.config = config if config is not None else {}
        self.initialize_services()

    def initialize_services(self):
        """初始化各推送服务"""
        self.services = {}

        # 邮件服务
        if self.config.get('mail', {}).get('enabled'):
            mail_config = self.config['mail']
            self.services['mail'] = MailService(mail_config)

        # 飞书服务
        if self.config.get('feishu', {}).get('enabled'):
            feishu_config = self.config['feishu']
            self.services['feishu'] = FeishuService(feishu_config)

        # 可以继续添加其他推送服务...

        print(f"推送器初始化完成，启用的服务: {list(self.services.keys())}")

    def send_message(self, title: str, content: str, message_type: str = "info") -> Dict[str, bool]:
        """
        发送消息到所有启用的推送服务

        Args:
            title: 消息标题
            content: 消息内容
            message_type: 消息类型 (info, success, warning, error)

        Returns:
            各服务推送结果字典 {service_name: success}
        """
        results = {}

        for service_name, service in self.services.items():
            try:
                success = service.send(title, content, message_type)
                results[service_name] = success
                print(f"{service_name} 推送{'成功' if success else '失败'}")
            except Exception as e:
                results[service_name] = False
                print(f"{service_name} 推送异常: {e}")

        return results


class MailService:
    """邮件推送服务"""

    def __init__(self, config: Dict):
        self.config = config

    def send(self, title: str, content: str, message_type: str) -> bool:
        """发送邮件"""
        try:
            # 创建邮件内容
            msg = MIMEText(content, 'plain', 'utf-8')
            msg['From'] = Header(self.config.get('address', ''), 'utf-8')
            msg['To'] = Header(self.config.get('receiver', ''), 'utf-8')  # 修正了这里的键
            msg['Subject'] = Header(title, 'utf-8')

            # 使用 STARTTLS 而不是 SMTP_SSL
            with smtplib.SMTP(self.config['host'], self.config['port']) as server:
                server.starttls()  # 启用加密连接
                server.login(self.config['address'], self.config['password'])
                server.send_message(msg)

            return True

        except Exception as e:
            print(f"邮件发送失败: {e}")
            return False


class FeishuService:
    """飞书群机器人推送服务（卡片消息）"""

    # message_type -> 飞书卡片 header 颜色
    _COLOR_MAP = {
        "info": "blue",
        "success": "green",
        "warning": "orange",
        "error": "red",
    }

    def __init__(self, config: Dict):
        self.config = config

    def send(self, title: str, content: str, message_type: str) -> bool:
        """发送飞书卡片消息"""
        try:
            time_stamp = str(int(round(time.time())))
            sign = self.gen_sign(time_stamp, self.config.get('signing_secret', ''))

            color = self._COLOR_MAP.get(message_type, "blue")

            # 将正文内容按换行拆分为多个 markdown 元素，保留段落结构
            content_elements = []
            for line in content.split("\n"):
                content_elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": line if line.strip() else "\u200b"  # 空行用零宽空格占位
                    }
                })

            card_body = {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title
                    },
                    "template": color
                },
                "elements": content_elements
            }

            payload = {
                "timestamp": time_stamp,
                "sign": sign,
                "msg_type": "interactive",
                "card": card_body
            }
            # 签名为空时不传（飞书要求无签名时去掉 sign/timestamp 字段也可，这里保留兼容）
            if not sign:
                payload.pop("sign", None)
                payload.pop("timestamp", None)

            response = requests.post(
                self.config['webhook'],
                headers={'Content-Type': 'application/json'},
                json=payload
            )

            result = response.json() if response.headers.get('Content-Type', '').startswith('application/json') else {}
            if response.status_code == 200 and result.get("code", 0) == 0:
                return True
            else:
                print(f"飞书卡片推送返回异常: status={response.status_code}, body={response.text}")
                return False

        except Exception as e:
            print(f"飞书消息发送失败: {e}")
            return False

    def gen_sign(self, timestamp: str, secret: str) -> str:
        """生成签名"""
        if not secret:
            return ""

        # 拼接timestamp和secret
        string_to_sign = '{}\n{}'.format(timestamp, secret)
        hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
        # 对结果进行base64处理
        sign = base64.b64encode(hmac_code).decode('utf-8')
        return sign


def send_notification(config: Dict, title: str, content: str, message_type: str = "info") -> Dict[str, bool]:
    """
    快速发送通知（一站式函数）

    Args:
        config: 推送配置
        title: 消息标题
        content: 消息内容
        message_type: 消息类型

    Returns:
        推送结果
    """
    notifier = Notifier(config)
    return notifier.send_message(title, content, message_type)
