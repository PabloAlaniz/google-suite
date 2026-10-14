#!/bin/bash -eu
# Build one fuzzer per fuzz/fuzz_*.py harness (run by ClusterFuzzLite).

pip3 install .

for harness in fuzz/fuzz_*.py; do
  name=$(basename "$harness" .py)
  compile_python_fuzzer "$harness"
  if [ -f "fuzz/dicts/$name.dict" ]; then
    cp "fuzz/dicts/$name.dict" "$OUT/$name.dict"
  fi
done
