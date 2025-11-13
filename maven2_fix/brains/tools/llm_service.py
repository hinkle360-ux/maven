from __future__ import annotations
import json
import hashlib
from pathlib import Path
from datetime import datetime
import http.client
import urllib.parse


class OllamaLLMService:
    """LLM service using a local Ollama instance with pattern learning.

    This service communicates with a local Ollama API (default
    http://localhost:11434) using Python's standard library.  It tracks all
    prompts and responses, hashes prompts to detect patterns, and
    automatically learns response templates when multiple similar responses
    are observed.  Learned templates are preferred over live LLM calls
    once they have been used successfully at least three times.
    """

    def __init__(self) -> None:
        # Load configuration from config/llm.json or fall back to defaults.
        self.config: dict = self._load_config()
        self.base_url: str = self.config.get("ollama_url", "http://localhost:11434")
        self.model: str = self.config.get("model", "llama3.2")
        self.enabled: bool = bool(self.config.get("enabled", True))
        # Determine root for storing patterns: navigate three parents up from this file.
        root = Path(__file__).resolve().parents[3]
        self.patterns_dir = root / "brains" / "personal" / "memory" / "learned_patterns"
        self.patterns_dir.mkdir(parents=True, exist_ok=True)
        self.interaction_log = self.patterns_dir / "llm_interactions.jsonl"
        self.templates_file = self.patterns_dir / "learned_templates.json"
        self.pattern_stats = self.patterns_dir / "pattern_stats.json"

    def _load_config(self) -> dict:
        """Load LLM configuration from config/llm.json if present.

        Returns a dictionary with default values if the file is absent or
        malformed.  Only standard library is used for IO and JSON parsing.
        """
        cfg_path = Path(__file__).resolve().parents[3] / "config" / "llm.json"
        if cfg_path.exists():
            try:
                with open(cfg_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh) or {}
                return data
            except Exception:
                pass
        # Default configuration
        return {
            "enabled": True,
            "provider": "ollama",
            "ollama_url": "http://localhost:11434",
            "model": "llama3.2",
            "learning": {
                "enabled": True,
                "min_interactions_to_learn": 10,
                "similarity_threshold": 0.8,
                "min_pattern_occurrences": 3,
            },
            "scheduling": {
                "learning_time": "02:00",
                "learning_enabled": True,
            },
        }

    def _hash_prompt(self, prompt: str) -> str:
        """Create a stable hash for the prompt for pattern matching."""
        normalized = " ".join(str(prompt or "").lower().split())
        return hashlib.md5(normalized.encode()).hexdigest()[:16]

    def call(
        self,
        prompt: str,
        max_tokens: int = 500,
        temperature: float = 0.7,
        context: dict | None = None,
    ) -> dict:
        """Call the local Ollama API or a learned template.

        Attempts to answer using a learned template first.  If no reliable
        template exists, calls the Ollama API over HTTP.  Returns a dict
        containing the response text, source and whether the LLM was used.
        """
        if not self.enabled:
            return {"ok": False, "error": "LLM disabled"}
        prompt_hash = self._hash_prompt(prompt)
        # Try a learned template
        template_res = self._try_template(prompt_hash, context)
        if template_res:
            return {
                "ok": True,
                "text": template_res["text"],
                "source": "learned_template",
                "confidence": template_res["confidence"],
                "llm_used": False,
            }
        # Fall back to calling the LLM via HTTP
        try:
            parts = urllib.parse.urlparse(self.base_url)
            conn = http.client.HTTPConnection(parts.hostname, parts.port or 80, timeout=30)
            # Build path: ensure /api/generate is appended
            path = parts.path.rstrip("/")
            if not path.endswith("/api"):
                path = path + "/api"
            path = path.rstrip("/") + "/generate"
            payload = json.dumps(
                {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                }
            )
            headers = {"Content-Type": "application/json"}
            conn.request("POST", path, body=payload, headers=headers)
            resp = conn.getresponse()
            if resp.status == 200:
                data = resp.read()
                try:
                    result = json.loads(data.decode())
                except Exception:
                    result = {}
                text = result.get("response", "")
                # Log the interaction for learning
                self._log_interaction(prompt, prompt_hash, text, context)
                return {
                    "ok": True,
                    "text": text,
                    "source": "ollama",
                    "llm_used": True,
                }
            # Non-200 response
            return {"ok": False, "error": f"Status {resp.status}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _try_template(self, prompt_hash: str, context: dict | None) -> dict | None:
        """Attempt to return a response from a learned template.

        A template is used only if it has succeeded at least three times
        previously (success_count >= 3).  Template metadata and usage counts
        are updated upon selection.
        """
        templates = self._load_templates()
        tpl = templates.get(prompt_hash)
        if tpl and tpl.get("success_count", 0) >= 3:
            # Update usage metadata
            tpl["use_count"] = tpl.get("use_count", 0) + 1
            tpl["last_used"] = datetime.now().isoformat()
            self._save_templates(templates)
            return self._apply_template(tpl, context)
        return None

    def _apply_template(self, template: dict, context: dict | None) -> dict:
        """Apply a learned template by substituting context variables."""
        text = template.get("response_template", "")
        if context:
            user = context.get("user") or {}
            user_name = user.get("name")
            if user_name and "{user_name}" in text:
                text = text.replace("{user_name}", str(user_name))
        return {
            "text": text,
            "confidence": template.get("confidence", 0.8),
        }

    def _log_interaction(
        self, prompt: str, prompt_hash: str, response: str, context: dict | None
    ) -> None:
        """Append a single interaction record to the log for learning."""
        record = {
            "timestamp": datetime.now().isoformat(),
            "prompt_hash": prompt_hash,
            "prompt": prompt[:200],
            "response": response,
            "context": {
                "query_type": (context or {}).get("query_type"),
                "user_name": (context or {}).get("user", {}).get("name"),
            },
        }
        try:
            with open(self.interaction_log, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
        except Exception:
            pass

    def _load_interactions(self) -> list:
        """Read all logged interactions for learning."""
        if not self.interaction_log.exists():
            return []
        interactions: list = []
        try:
            with open(self.interaction_log, "r", encoding="utf-8") as fh:
                for ln in fh:
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        interactions.append(json.loads(ln))
                    except Exception:
                        continue
        except Exception:
            pass
        return interactions

    def _load_templates(self) -> dict:
        """Load all learned templates from disk."""
        if self.templates_file.exists():
            try:
                with open(self.templates_file, "r", encoding="utf-8") as fh:
                    return json.load(fh) or {}
            except Exception:
                pass
        return {}

    def _save_templates(self, templates: dict) -> None:
        """Persist templates back to disk."""
        try:
            with open(self.templates_file, "w", encoding="utf-8") as fh:
                json.dump(templates, fh, indent=2)
        except Exception:
            pass

    def learn_patterns(self) -> None:
        """Analyse logged interactions and create or update templates.

        This function groups interactions by prompt hash and identifies
        consistent response patterns.  A template is created when there are
        at least ``min_pattern_occurrences`` instances and the computed
        similarity between responses exceeds ``similarity_threshold``.
        """
        if not self.config.get("learning", {}).get("enabled", True):
            return
        interactions = self._load_interactions()
        min_occ = int(
            self.config.get("learning", {}).get("min_pattern_occurrences", 3)
        )
        if len(interactions) < min_occ:
            return
        threshold = float(
            self.config.get("learning", {}).get("similarity_threshold", 0.8)
        )
        # Group interactions by prompt hash
        groups: dict = {}
        for rec in interactions:
            h = rec.get("prompt_hash")
            if not h:
                continue
            groups.setdefault(h, []).append(rec)
        templates = self._load_templates()
        for h, recs in groups.items():
            if len(recs) < min_occ:
                continue
            responses = [str(r.get("response", "")) for r in recs]
            sim = self._compute_similarity(responses)
            if sim >= threshold:
                template_text = self._generalize_responses(responses)
                templates[h] = {
                    "prompt_pattern": recs[0].get("prompt"),
                    "response_template": template_text,
                    "confidence": sim,
                    "success_count": len(recs),
                    "created_at": datetime.now().isoformat(),
                    "use_count": templates.get(h, {}).get("use_count", 0),
                    "examples": recs[:3],
                }
        self._save_templates(templates)
        self._update_stats(templates)

    def _compute_similarity(self, responses: list) -> float:
        """Compute Jaccard similarity across multiple response texts."""
        if len(responses) < 2:
            return 0.0
        term_sets = []
        for resp in responses:
            toks = set(str(resp).lower().split())
            term_sets.append(toks)
        common = set.intersection(*term_sets) if term_sets else set()
        all_terms = set.union(*term_sets) if term_sets else set()
        return len(common) / len(all_terms) if all_terms else 0.0

    def _generalize_responses(self, responses: list) -> str:
        """Return the most frequent response text from a list."""
        from collections import Counter

        counter = Counter(responses)
        return counter.most_common(1)[0][0] if counter else ""

    def _update_stats(self, templates: dict) -> None:
        """Write learning statistics to the stats file."""
        stats = {
            "last_learning_run": datetime.now().isoformat(),
            "total_templates": len(templates),
            "total_interactions": len(self._load_interactions()),
            "templates_by_usage": {},
        }
        for h, tpl in templates.items():
            count = tpl.get("use_count", 0)
            if count > 0:
                stats["templates_by_usage"][h] = count
        try:
            with open(self.pattern_stats, "w", encoding="utf-8") as fh:
                json.dump(stats, fh, indent=2)
        except Exception:
            pass

    def get_learning_stats(self) -> dict:
        """Return current learning statistics."""
        if self.pattern_stats.exists():
            try:
                with open(self.pattern_stats, "r", encoding="utf-8") as fh:
                    return json.load(fh) or {}
            except Exception:
                pass
        return {"templates": 0, "interactions": 0}


# Instantiate a global service for convenience
llm_service = OllamaLLMService()