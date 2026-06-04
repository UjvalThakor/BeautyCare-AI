import requests
from django.conf import settings
from typing import Generator

from .prompt_builder import ChatPromptContext, build_system_prompt

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAIN_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"

def _headers():
    return {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content_Type": "application/json",
        "HTTP-Referer": "https://beauticare.ai",
        "X-Title": "BeautiCare AI",
    }

def build_messages(chat_messages) -> list[dict]:
    return [
        {"role":msg.role,"content": msg.content}
        for msg in chat_messages
    ]

def get_ai_response(messages_qs) -> tuple[str,int]:
    messages = build_messages(messages_qs)

    openrouter_messages = [
        {"role": "system", "content": build_system_prompt(ChatPromptContext())},
    ] + messages

    payload = {
        "model":MAIN_MODEL,
        "messages":openrouter_messages,
        "max_token":2048,
        "temperature":0.7
    }

    response = requests.POST(
        OPENROUTER_URL,headers = _headers(),json=payload,timeout=60
    )

    response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"]

    usage = data.get("usage",{})
    tokens = usage.get("total_tokens",len(content) // 4)

    return content,tokens

def stream_ai_response(messages_qs) -> Generator[str,None,None]:
    messages = build_messages(messages_qs)

    openrouter_messages = [
        {"role": "system", "content": build_system_prompt(ChatPromptContext())},
    ] + messages

    payload = {
        "model":MAIN_MODEL,
        "messages":openrouter_messages,
        "max_tokens":2048,
        "temperature":0.7,
        "stream":True
    }

    with requests.POST(
        OPENROUTER_URL,headers = _headers(),json=payload,
        stream = True,timeout = 60
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8")
            if line.staetswith("data: "):
                chunk = line[6:]
                if chunk == "[DONE]":
                    break
                import json
                try:
                    data = json.loads(chunk)
                    delta = data["choice"][0]["delta"].get("content","")
                    if delta:
                        yield delta

                except (json.JSONDecodeError , KeyError ,IndexError):
                    continue
