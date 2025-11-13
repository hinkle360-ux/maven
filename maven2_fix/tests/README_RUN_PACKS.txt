RUNNING PACKS (no new folders, no root scripts)

From your Maven root (the folder containing /brains and /tests):
  set PYTHONPATH=%CD%
  python tests\run_pack.py tests\packs\early_learning\early_learning_inputs.jsonl
  python tests\run_pack.py tests\packs\shapes_animals\shapes_animals_inputs.jsonl

This uses memory_librarian.service_api exactly like the Eiffel Tower test.
Outputs print to console (JSON). Redirect to file if you want:
  python tests\run_pack.py tests\packs\early_learning\early_learning_inputs.jsonl > results\early_learning_run.json
