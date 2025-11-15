"""
Imaginer Brain
==============

The imaginer brain provides a safe sandbox for generating hypothetical
statements.  It allows the system to speculate without immediately
committing those speculations to long‑term memory.  Hypotheses are
tagged as transient and must be validated by the reasoning brain before
promotion to factual knowledge or working theory.

Operations:

  HYPOTHESIZE
      Accepts a ``prompt`` in the payload and returns a list of
      hypothetical statements.  Each hypothesis is returned as a dict
      with keys ``content`` and ``transient``.

The current implementation generates a single speculation by prefixing
the prompt with "It might be that".  Future versions could employ
more sophisticated mechanisms such as pattern completion or analogy.
"""

from __future__ import annotations
from typing import Dict, Any, List

def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    op = (msg or {}).get("op", "").upper()
    payload = (msg or {}).get("payload", {}) or {}
    if op == "HYPOTHESIZE":
        # Extract the prompt/topic.  If missing return an empty list.
        prompt = str(payload.get("prompt") or payload.get("topic") or "").strip()
        if not prompt:
            return {"ok": True, "op": op, "payload": {"hypotheses": []}}
        # Compose up to five speculative statements.  Each hypothesis is
        # transient and must be validated by the reasoning brain before
        # promotion to factual knowledge.  Different prefixes encourage
        # creative thinking without committing to memory.
        templates = [
            "It might be that {p}.",
            "Perhaps {p}.",
            "Imagine that {p}.",
            "One possibility is that {p}.",
            "Conceivably, {p}."
        ]
        hyps: List[Dict[str, Any]] = []
        for tmpl in templates:
            try:
                content = tmpl.format(p=prompt)
            except Exception:
                content = f"It might be that {prompt}."
            hyps.append({
                "content": content,
                "transient": True,
                "confidence": 0.4,
                "source": "imaginer"
            })
        # Respect any governance permit specifying max rollouts.  A permit
        # request is issued to the policy engine.  If the request is denied,
        # return an empty list.  Otherwise include the permit_id on each
        # hypothesis and truncate the list to the allowed number.
        try:
            n_requested = int(payload.get("n", len(hyps)))
        except Exception:
            n_requested = len(hyps)
        # Request a permit from governance
        permit_id = None
        allowed = True
        try:
            import importlib
            permits_mod = importlib.import_module(
                "brains.governance.policy_engine.service.permits"
            )
            perm_res = permits_mod.service_api({
                "op": "REQUEST",
                "payload": {"action": "IMAGINE", "n": n_requested}
            })
            perm_payload = perm_res.get("payload") or {}
            allowed = bool(perm_payload.get("allowed", False))
            permit_id = perm_payload.get("permit_id")
            # If denied, note the reason but drop hypotheses
            if not allowed:
                return {
                    "ok": True,
                    "op": op,
                    "payload": {"hypotheses": []}
                }
        except Exception:
            # On permit failure, proceed cautiously with allowed number but no proof
            permit_id = None
            allowed = True
        # Bound number of hypotheses.  Respect a configurable maximum
        # number of roll‑outs specified in ``config/imagination.json``.  This
        # allows deployments to tune the imagination sandbox depth without
        # modifying the code.  If the configuration is missing or invalid,
        # default to the length of the available templates (currently 5).
        max_rollouts = len(hyps)
        try:
            from pathlib import Path
            # Determine repository root (maven_extracted/maven) relative to this file
            root = Path(__file__).resolve().parents[4]
            cfg_path = root / "config" / "imagination.json"
            if cfg_path.exists():
                import json as _json
                with open(cfg_path, "r", encoding="utf-8") as cfgfh:
                    cfg = _json.load(cfgfh) or {}
                mr = int(cfg.get("max_rollouts", max_rollouts))
                # Ensure a sensible value (1 <= mr <= 20)
                if 1 <= mr <= 20:
                    max_rollouts = mr
        except Exception:
            # Fall back to default
            max_rollouts = len(hyps)
        # Limit n_requested by both available templates and configuration
        n = max(1, min(n_requested, max_rollouts, len(hyps)))
        hyps = hyps[:n]
        # Attach simple novelty scores and governance proof id
        out_hyps: List[Dict[str, Any]] = []
        for h in hyps:
            new_h = dict(h)
            # Score is a placeholder reflecting nominal novelty; could be extended
            new_h["score"] = 0.5
            if permit_id:
                new_h["permit_id"] = permit_id
            out_hyps.append(new_h)
        return {
            "ok": True,
            "op": op,
            "payload": {
                "hypotheses": out_hyps
            }
        }

    # EXECUTE_STEP: Phase 8 - Execute a creative/imagination step
    if op == "EXECUTE_STEP":
        step = payload.get("step") or {}
        step_id = payload.get("step_id", 0)
        context = payload.get("context") or {}

        # Extract step details
        description = step.get("description", "")
        step_input = step.get("input") or {}
        task = step_input.get("task", description)

        # Use HYPOTHESIZE to generate creative ideas
        hyp_result = service_api({"op": "HYPOTHESIZE", "payload": {"prompt": task, "n": 3}})

        if hyp_result.get("ok"):
            hyp_payload = hyp_result.get("payload") or {}
            hypotheses = hyp_payload.get("hypotheses", [])

            output = {
                "ideas": [h.get("content") for h in hypotheses],
                "hypotheses": hypotheses,
                "task": task
            }

            return {"ok": True, "payload": {
                "output": output,
                "patterns_used": ["creative:brainstorming"]
            }}

        return {"ok": False, "error": {"code": "HYPOTHESIZE_FAILED", "message": "Failed to generate ideas"}}

    return {"ok": False, "op": op, "error": "unknown operation"}

# Ensure the imaginer brain exposes a `handle` entry point
try:
    handle = service_api  # type: ignore[assignment]
    service_api = handle  # type: ignore[assignment]
except Exception:
    pass