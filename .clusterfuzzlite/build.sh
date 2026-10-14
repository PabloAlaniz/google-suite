#!/bin/bash -eu
# Build one fuzzer per fuzz/fuzz_*.py harness (run by ClusterFuzzLite).

# Dependencies pinned by hash, then the SDK itself as a locally built wheel
# without resolving anything (the forms Scorecard recognizes as pinned)
pip3 install --require-hashes -r .clusterfuzzlite/requirements.txt
pip3 wheel --no-deps --wheel-dir /tmp/sdk-wheel .
pip3 install --no-deps /tmp/sdk-wheel/*.whl

for harness in fuzz/fuzz_*.py; do
  name=$(basename "$harness" .py)
  compile_python_fuzzer "$harness"
  if [ -f "fuzz/dicts/$name.dict" ]; then
    cp "fuzz/dicts/$name.dict" "$OUT/$name.dict"
  fi
done
