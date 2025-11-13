import os, re, shutil

ROOT = os.path.dirname(os.path.dirname(__file__))
TARGETS = {
    'reasoning': os.path.join(ROOT, 'brains', 'cognitive', 'reasoning', 'service', 'reasoning_brain.py'),
    'librarian': os.path.join(ROOT, 'brains', 'cognitive', 'memory_librarian', 'service', 'memory_librarian.py'),
    'language':  os.path.join(ROOT, 'brains', 'cognitive', 'language', 'service', 'language_brain.py'),
}

def backup(path):
    b = path + '.bak'
    if not os.path.exists(b):
        shutil.copy2(path, b)
    return b

def replace_service_api(path, new_body):
    txt = open(path, 'r', encoding='utf-8').read()
    m = re.search(r'^\s*def\s+service_api\s*\(.*\):', txt, flags=re.M)
    if not m:
        return False, 'service_api() not found'
    start = m.start()
    tail = txt[m.end():]
    n = re.search(r'^\s*def\s+\w+\s*\(|^\s*class\s+\w+\s*:|^\s*if\s+__name__\s*==', tail, flags=re.M)
    end = len(txt) if not n else m.end() + n.start()
    new_txt = txt[:start] + new_body + '\n' + txt[end:]
    open(path, 'w', encoding='utf-8').write(new_txt)
    return True, 'service_api() replaced'

def patch_reasoning():
    path = TARGETS['reasoning']
    if not os.path.exists(path):
        return False, 'file missing'
    backup(path)

    new_body = (
        'def service_api(msg: dict) -> dict:\n'
        '    op = str(msg.get("op", "")).upper()\n'
        '    payload = msg.get("payload") or {}\n'
        '\n'
        '    def _is_question(txt: str) -> bool:\n'
        '        t = (txt or "").strip().lower()\n'
        '        if not t:\n'
        '            return False\n'
        '        if t.endswith("?"):\n'
        '            return True\n'
        '        return t.split(" ", 1)[0] in ("do","does","did","is","are","can","will","should","could","would","was","were")\n'
        '\n'
        '    def _score_evidence(results, text: str):\n'
        '        best = None\n'
        '        best_conf = 0.0\n'
        '        for rec in results or []:\n'
        '            try:\n'
        '                c = float(rec.get("confidence", 0.0))\n'
        '            except Exception:\n'
        '                c = 0.0\n'
        '            if c > best_conf and str(rec.get("content", "")).strip():\n'
        '                best, best_conf = rec, c\n'
        '        return best_conf, best\n'
        '\n'
        '    if op == "EVALUATE_FACT":\n'
        '        proposed = (payload or {}).get("proposed_fact") or {}\n'
        '        original_query = (payload or {}).get("original_query", "")\n'
        '        content = str(proposed.get("content", "")).strip()\n'
        '        evidence = (payload or {}).get("evidence") or {}\n'
        '        results = evidence.get("results") or []\n'
        '\n'
        '        if _is_question(original_query or content):\n'
        '            conf, best = _score_evidence(results, content)\n'
        '            verdict = "UNANSWERED"\n'
        '            mode = "QUESTION_INPUT"\n'
        '            src = None\n'
        '            if best and conf >= 0.85:\n'
        '                verdict, mode, src = "TRUE", "ANSWERED", best.get("id")\n'
        '            elif best and conf >= 0.5:\n'
        '                verdict, mode = "THEORY", "PARTIAL_ANSWER"\n'
        '            return {\n'
        '                "ok": True,\n'
        '                "verdict": verdict,\n'
        '                "confidence": conf,\n'
        '                "mode": mode,\n'
        '                "answer_source_id": src,\n'
        '                "supported_by": [best.get("id")] if best else [],\n'
        '                "contradicted_by": [],\n'
        '            }\n'
        '\n'
        '        try:\n'
        '            conf = float(proposed.get("confidence", 0.0))\n'
        '        except Exception:\n'
        '            conf = 0.0\n'
        '        verdict = "TRUE" if conf >= 0.85 else ("THEORY" if conf >= 0.5 else "UNKNOWN")\n'
        '        return {\n'
        '            "ok": True,\n'
        '            "verdict": verdict,\n'
        '            "confidence": conf,\n'
        '            "mode": "STATEMENT_INPUT",\n'
        '            "supported_by": [],\n'
        '            "contradicted_by": [],\n'
        '        }\n'
        '\n'
        '    return {"ok": False, "error": "UNSUPPORTED_OP", "op": op}\n'
    )
    return replace_service_api(path, new_body)

def patch_librarian():
    path = TARGETS['librarian']
    if not os.path.exists(path):
        return False, 'file missing'
    backup(path)

    txt = open(path, 'r', encoding='utf-8').read()

    if '_is_question(' not in txt:
        txt = re.sub(
            r'(from\s+[^\n]+\n|import\s+[^\n]+\n)+',
            r'\g<0>\n\ndef _is_question(txt: str) -> bool:\n    t = (txt or "").strip().lower()\n    if not t:\n        return False\n    if t.endswith("?"):\n        return True\n    return t.split(" ", 1)[0] in ("do","does","did","is","are","can","will","should","could","would","was","were")\n\n',
            txt, count=1)

    txt = re.sub(
        r"_brain_module\(\s*['\"]reasoning['\"]\s*\)\.service_api\(\s*\{\s*['\"]op['\"]\s*:\s*['\"]EVALUATE_FACT['\"]\s*,\s*['\"]payload['\"]\s*:\s*\{[^}]*\}\s*\}\s*\)",
        '_brain_module("reasoning").service_api({"op": "EVALUATE_FACT", "payload": {"proposed_fact": {"content": proposed_content or text, "confidence": conf, "source": "user_input"}, "original_query": text, "evidence": ctx.get("stage_2R_memory") or {}}})',
        txt, count=1, flags=re.S)

    if 'stage_9_storage' in txt and 'question_answer_path' not in txt:
        txt = re.sub(
            r'(ctx\[\s*["\']stage_8_validation["\']\s*\]\s*=\s*[^\n]+\n)',
            r'\1        if _is_question(text) or str((ctx.get("stage_8_validation") or {}).get("mode", "")).upper() in ("ANSWERED", "PARTIAL_ANSWER"):\n            ctx["stage_9_storage"] = {"skipped": True, "reason": "question_answer_path"}\n            return success_response(op, mid, ctx)\n',
            txt, count=1, flags=re.S)

    open(path, 'w', encoding='utf-8').write(txt)
    return True, 'librarian patched'

def patch_language():
    path = TARGETS['language']
    if not os.path.exists(path):
        return False, 'file missing'
    backup(path)

    txt = open(path, 'r', encoding='utf-8').read()

    if 'QUESTION_INPUT' not in txt and 'ANSWERED' not in txt:
        block = (
            "\n    # --- Tier-2: speak the answer for questions ---\n"
            "    val = (ctx.get('stage_8_validation') or {})\n"
            "    mode = str(val.get('mode','')).upper()\n"
            "    if mode in ('ANSWERED','PARTIAL_ANSWER','QUESTION_INPUT'):\n"
            "        q = (ctx.get('stage_1_input') or {}).get('text','')\n"
            "        conf = float(val.get('confidence',0.0) or 0.0)\n"
            "        if mode=='ANSWERED' and conf>=0.85:\n"
            "            reply = 'Yes.'\n"
            "        elif mode=='PARTIAL_ANSWER':\n"
            "            reply = 'I think so, but I am not fully sure yet.'\n"
            "        else:\n"
            "            reply = 'I do not know yet.'\n"
            "        ctx.setdefault('stage_13_language',{})['final']=reply\n"
            "        return success_response(op, mid, ctx)\n"
        )
        if 'return success_response(op, mid, ctx)' in txt:
            txt = txt.rsplit('return success_response(op, mid, ctx)', 1)
            txt = txt[0] + block + '    return success_response(op, mid, ctx)' + txt[1]
        else:
            txt += block

    open(path, 'w', encoding='utf-8').write(txt)
    return True, 'language patched'

def main():
    for name, fn in (('reasoning', patch_reasoning), ('librarian', patch_librarian), ('language', patch_language)):
        ok, msg = fn()
        print('{}: {} - {}'.format(name, 'OK' if ok else 'FAIL', msg))

if __name__ == '__main__':
    main()
