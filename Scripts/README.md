# Evaluation Statistics Scripts

Run the main checker from the repository root:

```bash
python3 Scripts/evaluation_numbers.py
```

The script recomputes the Evaluation-section numbers from the checked-in
artifacts under `Result/`, `CoqStoq/`, and `CoqGym/`: Cobblestone and
PALM comparisons, the reported ReCent-Prover comparison, general-agent
success and shared-solved cost/time tables, ablation statistics, Parcas
results, and proof-step distribution statistics.
