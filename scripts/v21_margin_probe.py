#!/usr/bin/env python3
"""v2.1 dense-text margin experiment for lcm-hygiene (2026-08-26).

Measures, per candidate chars-budget, how the local llama-server tokenizes
worst-case dense ASCII (hex/base64 blobs) vs normal prose. Grounds the v2.1
margin decision in measured server-side counts instead of the chars/4 guess.

Usage:
    HERMES_HOME=/home/hermes-pi/.hermes \
    /home/hermes-pi/.hermes/hermes-agent/venv/bin/python scripts/v21_margin_probe.py

Read-only against :8080 except for 1-token completions; never touches lcm.db.
"""
import json
import random
import sys
import time
import urllib.request

BUDGET = 3000          # llm_input_tokens in production guard
PROBE_CHARS = [12000, 9000, 8000, 6000, 4200, 3600]
SCALES = {
    'prose': lambda n: ("The user asked about deployment and we reviewed logs. " * (n // 55))[:n],
    'code': lambda n: ("def handler(req):\n    return json.dumps({'ok': True})\n" * (n // 44))[:n],
    'hex': lambda n: ''.join(random.choice('abcdef0123456789') for _ in range(n)),
}


def server_tokens(text):
    req = urllib.request.Request(
        'http://127.0.0.1:8080/v1/chat/completions',
        data=json.dumps({'model': 'x', 'max_tokens': 1,
                         'messages': [{'role': 'user', 'content': text}]}).encode(),
        headers={'Content-Type': 'application/json'})
    t0 = time.time()
    try:
        r = json.load(urllib.request.urlopen(req, timeout=180))
        return r['usage']['prompt_tokens']
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read())['error']['message']
            return int(msg.split('(')[1].split()[0])   # exceed_context_size_error path
        except Exception:
            return None
    except Exception:
        return None


def main():
    random.seed(5)
    print(f'budget={BUDGET} server=n_ctx-4096 Qwen2.5-0.5B @ :8080')
    print(f'{"scale":>6} {"chars":>6} {"server_tok":>10} {"tok_per_1k_chars":>16}')
    worst_ratio = {}
    for scale_name, gen in SCALES.items():
        for n in PROBE_CHARS:
            text = gen(n)
            st = server_tokens(text)
            if isinstance(st, int):
                ratio = st / (n / 1000.0)
                worst_ratio[scale_name] = max(worst_ratio.get(scale_name, 0), ratio)
                flag = ' <-- OVER' if st > BUDGET + 400 else ''
                print(f'{scale_name:>6} {n:>6} {st:>10} {ratio:>16.0f}{flag}', flush=True)
            else:
                print(f'{scale_name:>6} {n:>6} {"timeout":>10}', flush=True)
    print()
    print('Worst tokens-per-1000-chars observed:')
    for k, v in worst_ratio.items():
        safe_budget = int(BUDGET * 1000 / v)
        print(f'  {k:>6}: {v:.0f}/1k chars -> safe chars budget ~= {safe_budget}')


if __name__ == '__main__':
    main()
