#!/bin/bash
# Run every question in questions.txt and save the output to a file.
# Usage:  ./run_eval.sh grounded     (or)  ./run_eval.sh stripped
#
# The label is just for the output filename, it does NOT change rag.py.
# Edit the system_prompt in rag.py yourself between runs.

LABEL=${1:-run}
OUT="eval_${LABEL}.txt"
: > "$OUT"

n=0
while IFS= read -r q; do
  [ -z "$q" ] && continue
  n=$((n+1))
  echo "=========================================" | tee -a "$OUT"
  echo "[$n] $q" | tee -a "$OUT"
  echo "-----------------------------------------" | tee -a "$OUT"
  python rag.py ask --question "$q" 2>&1 | tee -a "$OUT"
  echo "" | tee -a "$OUT"
done < questions.txt

echo "Done. $n questions. Saved to $OUT"
