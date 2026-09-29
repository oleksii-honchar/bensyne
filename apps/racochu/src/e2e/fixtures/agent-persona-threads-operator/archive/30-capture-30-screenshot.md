---
id: 30-capture-30-screenshot
title: "Take screenshot and extract PNG from JSON response"
entry: false
conditions:
  - "part is in view in the chrome-debug viewport (pageId from navigator)"
veto:
  - "proceeding with an unread/untouched screenshot JSON result file (mandatory extraction step)"
edges:
  - target: 30-capture/40-ocr.md
    when: "screenshot PNG extracted and saved successfully"
created: 2026-09-03
updated: 2026-09-03
status: active
---
# Take screenshot and extract PNG from JSON response

**Before starting:** Record your traversal transition to this node in your session memory bank.

Take a screenshot of the current viewport using the chrome-debug instance (take_screenshot, format: png). **Critical gotcha:** The tool does NOT return the image inline — it returns a JSON tool-response file auto-saved under `tool-responses/` with a base64 data URL at `.result.attachments[0].url`. You MUST extract and save it as a PNG:

```bash
python3 -c "
import json, base64
with open('tool-responses/chrome-devtools_take_screenshot-<ts>.json') as f:
    d = json.load(f)
url = d['result']['attachments'][0]['url']
img = base64.b64decode(url.split(',',1)[1])
with open('tool-responses/chrome-devtools_take_screenshot-<ts>.png','wb') as f:
    f.write(img)
"
```

Then copy the PNG to `materials/screenshots/<partId>-part<N>-<seq>.png`. The tool may also save under the session's `tool-responses/` — if a custom filePath is outside configured workspace roots, use the JSON extraction path.
