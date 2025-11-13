
from __future__ import annotations
# test run_maven patch inserted
import json, importlib.util, sys
from pathlib import Path
from api.utils import generate_mid

HERE = Path(__file__).resolve().parent
# Ensure the project root (this directory) is on sys.path so that local
# packages like ``api`` and ``ui`` can be imported when there is no nested
# ``maven`` package present.  This mirrors the dynamic import logic used in
# other entry points such as ``maven/ui/maven_chat.py``.
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
lib = HERE / "brains" / "cognitive" / "memory_librarian" / "service" / "memory_librarian.py"
spec = importlib.util.spec_from_file_location("memory_librarian", lib)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

if __name__ == "__main__":
    """
    When invoked as a script, this entry point will launch the natural language
    chat interface if no command line arguments are provided.  Otherwise, it
    treats the first argument as a query and an optional second argument as a
    confidence value and executes the full Maven pipeline on that input.  This
    dual behaviour makes `run_maven.py` both a convenient button to start
    interactive conversation and a quick way to test the pipeline with a
    single query.
    """
    # Start the learning daemon for pattern analysis.  The daemon runs in
    # a background thread and periodically calls the LLM service to learn
    # new templates from logged interactions.  If the import fails or
    # scheduling is disabled, the daemon is skipped silently.
    try:
        from brains.agent.learning_daemon import LearningDaemon  # type: ignore
        import threading
        _learning_daemon = LearningDaemon()
        # Only start the daemon if learning is enabled
        if getattr(_learning_daemon, "learning_enabled", True):
            _ld_thread = threading.Thread(
                target=_learning_daemon.start_scheduled, daemon=True
            )
            _ld_thread.start()
    except Exception:
        # If anything goes wrong, do not block startup; the pipeline
        # continues without background learning.
        _learning_daemon = None

    # Parse an optional --mode argument.  Supported values are "architect"
    # (the default) and "execution".  Architect mode prints the full JSON
    # response (including reasoning context), while execution mode
    # suppresses verbose context and prints only the final answer and
    # confidence if available.
    # Remove the flag and its value from sys.argv before processing
    mode = "architect"
    args = sys.argv[1:]
    if "--mode" in args:
        try:
            idx = args.index("--mode")
            if idx + 1 < len(args):
                mode = args[idx + 1].strip().lower() or mode
                # Remove the flag and value
                del args[idx:idx + 2]
        except Exception:
            # Leave mode unchanged if parsing fails
            pass

    # If no additional arguments remain, start the interactive chat
    if not args:
        try:
            # Import the chat interface from the UI package lazily.
            from ui.maven_chat import repl as chat_repl  # type: ignore
            chat_repl()
        except Exception:
            # Fallback: run a default pipeline example in the selected mode
            text = "The cell divides by mitosis."
            conf = 0.8
            resp = mod.service_api({"op": "RUN_PIPELINE", "mid": generate_mid(), "payload": {"text": text, "confidence": conf}})
            if mode == "execution":
                try:
                    ctx = (resp.get("payload") or {}).get("context") or {}
                    final_ans = ctx.get("final_answer")
                    final_conf = ctx.get("final_confidence")
                    if final_ans is not None:
                        print(json.dumps({"final_answer": final_ans, "final_confidence": final_conf}, indent=2, ensure_ascii=False))
                    else:
                        print(json.dumps(resp, indent=2))
                except Exception:
                    print(json.dumps(resp, indent=2))
            else:
                # Architect mode: show final answer if available for brevity
                try:
                    ctx = (resp.get("payload") or {}).get("context") or {}
                    final_ans = ctx.get("final_answer")
                    final_conf = ctx.get("final_confidence")
                    if final_ans is not None:
                        print(json.dumps({"final_answer": final_ans, "final_confidence": final_conf}, indent=2, ensure_ascii=False))
                    else:
                        print(json.dumps(resp, indent=2))
                except Exception:
                    print(json.dumps(resp, indent=2))
    else:
        # Use provided arguments to run the pipeline on a single input
        # Remaining args correspond to query and optional confidence
        text = args[0] if len(args) >= 1 else "The cell divides by mitosis."
        try:
            conf = float(args[1]) if len(args) >= 2 else 0.8
        except Exception:
            conf = 0.8
        # Before running the pipeline, consolidate memory tiers.  This ensures
        # that high‑importance facts from previous sessions are promoted into
        # mid‑ and long‑term stores and available for retrieval.  Errors are
        # swallowed to avoid disrupting normal pipeline execution.
        try:
            from brains.cognitive.memory_consolidation import consolidate_memories  # type: ignore
            consolidate_memories()
        except Exception:
            pass
        resp = mod.service_api({"op": "RUN_PIPELINE", "mid": generate_mid(), "payload": {"text": text, "confidence": conf}})
        if mode == "execution":
            try:
                ctx = (resp.get("payload") or {}).get("context") or {}
                final_ans = ctx.get("final_answer")
                final_conf = ctx.get("final_confidence")
                if final_ans is not None:
                    print(json.dumps({"final_answer": final_ans, "final_confidence": final_conf}, indent=2, ensure_ascii=False))
                else:
                    print(json.dumps(resp, indent=2))
            except Exception:
                print(json.dumps(resp, indent=2))
        else:
            # Architect mode: show final answer if available for brevity
            try:
                ctx = (resp.get("payload") or {}).get("context") or {}
                final_ans = ctx.get("final_answer")
                final_conf = ctx.get("final_confidence")
                if final_ans is not None:
                    print(json.dumps({"final_answer": final_ans, "final_confidence": final_conf}, indent=2, ensure_ascii=False))
                else:
                    print(json.dumps(resp, indent=2))
            except Exception:
                print(json.dumps(resp, indent=2))
