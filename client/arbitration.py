


# --------------------------------------------

import time
import json
import os
import requests
import prompts
from utils import logger
from utils.redis_tool import RedisClient


TIMEOUT = 2.0
MAX_HIS = 6
TTL = 60
CHUNK_SIZE = 1024
MAX_TOKEN = 2048
REDIS_KEY = "voice:arbitration_history:"
_redis_client = RedisClient() 


API_KEY = os.environ["API_KEY"]
DOUBAO_URL = os.environ["BASE_URL"]


SYSTEM_PROMPT = prompts.EMOTION_ROUTE_SYSTEM_PROMPT


def request_arbitration(query, sender_id):
    headers = {
        "Content-Type": "application/json",
        "Authorization": API_KEY
    }
    message = [{"role": "system", "content": SYSTEM_PROMPT}]

    try:
        history = _redis_client.get(REDIS_KEY + sender_id)
        history = json.loads(history) if history else []
        history.append({"role": "user", "content": query})
        message.extend(history)

        body = dict(
            model="ep-20250822163757-hs876",
            messages=message,
            max_tokens=10,
            temperature=0,
            stream=True
        )

        response = requests.post(
            DOUBAO_URL,
            headers=headers,
            json=body,
            stream=True,
            timeout=TIMEOUT
        )

        text = "E"
        for r in response.iter_lines(chunk_size=CHUNK_SIZE):
            if not r:
                continue
            r = r.decode("utf-8").lstrip("data: ")
            if r == "[DONE]":
                break
            r = json.loads(r)
            text = r["choices"][0]["delta"]["content"]
            if text:
                break

        if text not in ["E", "G"]:
            text = "E"

        history.append({"role": "assistant", "content": text})
        history = history[-MAX_HIS:]
        _redis_client.set(
            REDIS_KEY + sender_id,
            json.dumps(history, ensure_ascii=False),
            ex=TTL
        )

        return text

    except Exception as e:
        logger.info(f"Arbitration API error: {e}")
        return "E"
