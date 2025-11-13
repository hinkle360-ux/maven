# 🧠 Step 1 – Working Memory & Control Shell Integration

**Revision:** 2025‑11  
**Scope:** Stage 5 (Memory Librarian)  
**Focus:** Expose a simple shared working memory and lightweight control scheduler without changing the sequential broadcast pipeline or introducing new package roots.

---

## 1 · Background

Early prototypes of Maven’s *cognitive graph* introduced a separate “working memory” and “control shell” package. Those prototypes violated the upgrade rules (no new packages, no changes to the pipeline backbone) and were removed. Instead, the **Memory Librarian** now subsumes these roles in Step 1.

Working memory provides a short‑lived, shared scratchpad where cognitive modules can deposit hypotheses, intermediate results or evidence with confidence scores and expiration times. A lightweight scheduler scans this pad and emits events on the internal message bus. This design preserves the **strict broadcast order** – the librarian remains the sole hub and does not short‑circuit any stage – while laying the groundwork for a full cognitive graph in later phases.

## 2 · Service API Extensions

The memory librarian’s `service_api` now recognises four new operations. All calls are offline, use only the standard library, and respect the same governance rules as other librarian functions.

| Operation | Payload Fields | Behaviour |
|----------|---------------|-----------|
| `WM_PUT` | `key`, `value`, `tags` (list), `confidence` (float), `ttl` (seconds) | Stores an entry in the shared working memory. Each entry is timestamped and expires after `ttl`. |
| `WM_GET` | Optional `key`, optional `tags` | Returns a list of live working‑memory entries matching the key (exact) or any of the supplied tags. Confidence scores and creation times are included. |
| `WM_DUMP` | *(none)* | Returns **all** live working‑memory entries. This is intended for diagnostics. |
| `CONTROL_TICK` | *(none)* | Prunes expired entries and emits one `WM_EVENT` on the message bus per live entry. Events have the form `{from:'memory_librarian', to:'scheduler', type:'WM_EVENT', entry:{...}}`. Downstream modules can subscribe to these events to trigger deeper reasoning or arbitration. |

### Example

```python
from brains.cognitive.memory_librarian.service import memory_librarian

# Put a hypothesis into working memory
res = memory_librarian.service_api({
    "op": "WM_PUT",
    "payload": {
        "key": "hypothesis",
        "value": "The sun is a star",
        "tags": ["astronomy", "definition"],
        "confidence": 0.6,
        "ttl": 600
    }
})

# Retrieve all entries with the tag 'astronomy'
res = memory_librarian.service_api({
    "op": "WM_GET",
    "payload": {"tags": ["astronomy"]}
})

# Trigger scheduler and emit events
res = memory_librarian.service_api({"op": "CONTROL_TICK"})
```

## 3 · Compatibility Notes

- No new folders or `__init__.py` files were added. The *working memory* and *control shell* live entirely inside the existing **memory librarian**.
- The sequential broadcast order is unchanged. These operations are only called explicitly by clients or self‑DMN ticks; they do not shortcut any stage.
- Any previously created `working_memory` or `control_shell` package files should be removed. This document replaces those references.

## 4 · Next Steps

Step 1 lays the foundation for a richer cognitive graph. Subsequent releases will integrate hybrid semantic memory (vectors + symbols), adapt attention routing based on WM events, and introduce arbitration rules for competing hypotheses. For now, the focus is on providing a safe, shared scratchpad and a minimal event loop that can be inspected via offline tests.
