---
name: demo
description: Read and update demo sheets with the demo library and its demo CLI. Use for demo tasks.
license: MIT
metadata:
  openclaw:
    requires:
      env:
        - DEMO_TOKEN
    primaryEnv: DEMO_TOKEN
    install:
      - kind: pip
        package: "demo-lib[cli]"
        bins:
          - demo
---

# Demo

Set `DEMO_TOKEN` (and optionally `DEMO_TIMEOUT`).

```bash
demo read SHEET_KEY --range A1:B2 -o json
demo rows add --name Ana --no-notify
```

```python
from demo_lib import Client

client = Client(token="t")
sheet = client.open_by_key("abc")
sheet.update("A1", [["x"]])
for row in sheet.rows():
    print(row.name, row.label, row.tags)
found = client.find("Ana")
client.send(["a@b.c"], "hi", notify=True)
```

More in [the reference](references/more.md).
