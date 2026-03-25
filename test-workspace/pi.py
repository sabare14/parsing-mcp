import subprocess
prompt_text = "Find a constant or weight in test-workspace/config_auto_finder.py and increase it slightly and report from what to what has been changed"
result = subprocess.run(
    ["npx", "@mariozechner/pi-coding-agent"],
    input=prompt_text,
    text=True,
    capture_output=True
)

output = result.stdout
print(output)