from openai import OpenAI
import replicate
from .config import (
    OPENAI_API_KEY,
    REPLICATE_API_TOKEN,
    MODEL,
    OPENAI_BASE_URL,
    REASONING_EFFORT,
)
from .utils import *
import re


_client_kw = {'api_key': OPENAI_API_KEY}
if OPENAI_BASE_URL:
    _client_kw['base_url'] = OPENAI_BASE_URL
client = OpenAI(**_client_kw)


def _chat_completion_extra_kwargs() -> dict:
    """DeepSeek thinking mode (openai<1.40: pass via extra_body only)."""
    if OPENAI_BASE_URL and 'deepseek' in OPENAI_BASE_URL.lower():
        return {
            'extra_body': {
                'thinking': {'type': 'enabled'},
                'reasoning_effort': REASONING_EFFORT,
            },
        }
    return {}


system = 'You will be provided with a Coq proof state and related definitions and lemmas, your task is to give a proof.'

instruction = '''I will give you a Coq proof state, including both hypotheses and a specific goal and your need to prove it. Your response should be a singular code block of Coq proof starting with "```coq\n", ending with "Qed.```", without any additional explanation or commentary. Follow to these guidelines:
Introduce variables using unique names to avoid any conflicts.
Keep each command distinct and separated, avoid concatenations like ';' or '[cmd|cmd]'.
Organize your proof with bullets like '-', '+', and '*' instead of braces ({, }). Shift to their double symbols like '--' and '++', when necessary.
Effectively use given premises, follow the syntax and structure demonstrated in the examples provided.
'''

examples = '''
Example 1:

Hypotheses:
n, m: nat
IHn: m + n = n + m

Goal:
m + S n = S n + m

Your Response:
```coq
simpl. rewrite <- IHn. auto.
Qed.```

Example 2:
Hypotheses:

Goal:
forall n m : nat, m + n = n + m

Your Response:
```coq
intros n m. induction n.
- simpl. auto.
- simpl. rewrite <- IHn. auto.
Qed.```'''


def process_response(response: str):
    pattern = r'```coq\n(.*?)```'
    matches = re.findall(pattern, response, re.DOTALL)
    if matches:
        return matches[0]
    else:
        return response


def check_response(response: str):
    if not (response.startswith('```coq\n') and response.endswith('```')):
        return False
    return True


def _usage_int(usage, *keys, default=0):
    if usage is None:
        return default
    data = usage.model_dump() if hasattr(usage, 'model_dump') else usage
    if not isinstance(data, dict):
        return default
    for key in keys:
        val = data.get(key)
        if val is not None:
            return int(val)
    return default


def usage_from_completion(response) -> dict | None:
    """Normalize token usage (DeepSeek cache hit/miss, OpenAI cached_tokens, etc.)."""
    usage = getattr(response, 'usage', None)
    if usage is None:
        return None
    prompt_tokens = _usage_int(usage, 'prompt_tokens')
    completion_tokens = _usage_int(usage, 'completion_tokens')
    total_tokens = _usage_int(usage, 'total_tokens')
    if total_tokens == 0 and (prompt_tokens or completion_tokens):
        total_tokens = prompt_tokens + completion_tokens

    cache_hit = _usage_int(usage, 'prompt_cache_hit_tokens')
    cache_miss = _usage_int(usage, 'prompt_cache_miss_tokens')

    if cache_hit == 0 and cache_miss == 0 and prompt_tokens:
        details = getattr(usage, 'prompt_tokens_details', None)
        if details is not None:
            cached = _usage_int(details, 'cached_tokens')
            if cached:
                cache_hit = cached
                cache_miss = max(prompt_tokens - cached, 0)
        if cache_miss == 0 and cache_hit == 0:
            cache_miss = prompt_tokens

    reasoning_tokens = 0
    ctd = getattr(usage, 'completion_tokens_details', None)
    if ctd is not None:
        reasoning_tokens = _usage_int(ctd, 'reasoning_tokens')

    return {
        'prompt_tokens': prompt_tokens,
        'completion_tokens': completion_tokens,
        'total_tokens': total_tokens,
        'prompt_cache_hit_tokens': cache_hit,
        'prompt_cache_miss_tokens': cache_miss,
        'reasoning_tokens': reasoning_tokens,
    }


def format_usage_line(usage: dict) -> str:
    return (
        f"tokens: total={usage['total_tokens']} "
        f"cache_hit_read={usage['prompt_cache_hit_tokens']} "
        f"cache_miss_read={usage['prompt_cache_miss_tokens']} "
        f"write={usage['completion_tokens']}"
        + (f" reasoning={usage['reasoning_tokens']}" if usage.get('reasoning_tokens') else '')
    )


USAGE_KEYS = (
    'prompt_tokens',
    'completion_tokens',
    'total_tokens',
    'prompt_cache_hit_tokens',
    'prompt_cache_miss_tokens',
    'reasoning_tokens',
)


def _empty_usage() -> dict:
    return {k: 0 for k in USAGE_KEYS}


_run_usage_total = _empty_usage()
_run_usage_call_count = 0


def reset_run_usage() -> None:
    global _run_usage_total, _run_usage_call_count
    _run_usage_total = _empty_usage()
    _run_usage_call_count = 0


def add_run_usage(snap: dict) -> None:
    global _run_usage_call_count
    _run_usage_call_count += 1
    for key in USAGE_KEYS:
        _run_usage_total[key] += snap.get(key, 0)


def run_usage_summary() -> dict:
    return {
        'total': dict(_run_usage_total),
        'api_calls': _run_usage_call_count,
    }


def print_run_usage(prefix: str = '[LLM usage run total]') -> None:
    if _run_usage_call_count == 0:
        print(f'{prefix} (no API calls)')
        return
    print(f'{prefix} calls={_run_usage_call_count} ' + format_usage_line(_run_usage_total))


class LLM:
    def __init__(self, max_tokens=None):
        from .config import llm_max_tokens as _default_max_tokens

        self.max_tokens = _default_max_tokens if max_tokens is None else int(max_tokens)
        self.retry_limit = 2
        self.api_key: str
        self.history_query = []
        self.history_response = []
        self.messages = [
                {"role": "system", "content": system},
            ]
        self.length = [trim_prompt(p['content'])[0] for p in self.messages]
        self.usage_calls: list[dict] = []
        self.usage_total = _empty_usage()

    
    def get_prompt(self, goals, premises, defs):
        prompt = instruction + examples
        assert goals != [], 'goals is [] before querying'
        
        goal = goals[0]
        prompt += '\n\nSolve This Proof State:\n\n'
        prompt += 'Hypotheses:\n{hypos}\n\nGoal:\n{goal}\n\n'\
                    .format(hypos='\n'.join([f'{k}: {v}' for k, v in goal['hypos'].items()]) if goal['hypos'] else 'None', goal=goal['goal'])
        if defs != [] or premises != []:
            prompt += 'Premises:'
        if defs != []:
            num_tokens = self.max_tokens - sum(self.length) - trim_prompt(prompt)[0]
            tokens_one = int(num_tokens/(len(defs)+len(premises)))
            prompt += '\n{defs}' \
                .format(defs= '\n'.join([trim_prompt(d, tokens_one)[1] for d in defs]))
        if premises != []:
            num_tokens = self.max_tokens - sum(self.length) - trim_prompt(prompt)[0]
            tokens_one = int(num_tokens/len(premises))
            prompt += '\n{lemmas}' \
                .format(lemmas= '\n'.join([trim_theorem(p, tokens_one)[1] for p in premises]))
        return prompt

    def _record_usage(self, response) -> None:
        snap = usage_from_completion(response)
        if snap is None:
            return
        self.usage_calls.append(snap)
        for key in self.usage_total:
            self.usage_total[key] += snap.get(key, 0)
        add_run_usage(snap)
        print('[LLM usage] ' + format_usage_line(snap))
        if len(self.usage_calls) > 1:
            print('[LLM usage total] ' + format_usage_line(self.usage_total))

    def usage_summary(self) -> dict:
        return {'total': dict(self.usage_total), 'calls': list(self.usage_calls)}

    def query(self, prompt: str):
        if 'llama' in MODEL.lower() and not MODEL.lower().startswith('gpt'):
            out = self.query_llama(prompt)
        else:
            out = self.query_gpt(prompt)
        if out is None:
            raise RuntimeError(
                f'LLM returned no text (MODEL={MODEL!r}). '
                'Check OPENAI_API_KEY, OPENAI_BASE_URL, and model id.'
            )
        return out


    def query_llama(self, prompt: str):
        length, prompt = trim_prompt(prompt, self.max_tokens-sum(self.length))
        self.messages.append({'role': 'user', 'content': prompt})
        self.length.append(length)

        input = {
            "max_tokens": 1000,
            "min_tokens": 0,
            "temperature": 0.75,
            "system_prompt": system,
            "prompt": prompt,
            "prompt_template": "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\nYou will be provided with a Coq proof state and related definitions and lemmas, your task is to give a proof.<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n{prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n",
            "length_penalty": 1,
            "stop_sequences": "<|end_of_text|>,<|eot_id|>",
            "presence_penalty": 1.15,
            "log_performance_metrics": False
        }

        output = replicate.run(
            MODEL,
            input=input
        )
        output = ''.join(output)
        print(output)
        self.messages.append({'role': 'assistant', 'content': output})
        return process_response(output)


    def query_gpt(self, prompt: str):
        length, prompt = trim_prompt(prompt, self.max_tokens-sum(self.length))
        self.messages.append({'role': 'user', 'content': prompt})
        self.length.append(length)
        # gpt-4o-2024-05-13
        response = client.chat.completions.create(
            model=MODEL,
            messages=self.messages,
            **_chat_completion_extra_kwargs(),
        )
        self._record_usage(response)
        role = response.choices[0].message.role
        content = response.choices[0].message.content
        if content is None:
            return None
        self.messages.append({'role': role, 'content': content})
        return process_response(content)
    

    def batch_record(self, custom_id, prompt):
        length, prompt = trim_prompt(prompt, self.max_tokens-sum(self.length))
        self.messages.append({'role': 'user', 'content': prompt})
        record = {
            "custom_id": custom_id, 
            "method": "POST", 
            "url": "/v1/chat/completions", 
            "body": {
                "model": "gpt-3.5-turbo-0125", 
                "messages": self.messages,
                "max_tokens": 1000
                }
            }
        return record


    def log(self):
        return {
            'messages': self.messages[1:],
            'token_usage': self.usage_summary(),
        }
        

if __name__ == '__main__':
    pass
    
    
