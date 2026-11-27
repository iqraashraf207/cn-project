#!/usr/bin/env python3
"""generates the test page (index.html + 20 objects of 10 KB each) in server/www/."""
import os
import random

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "www")
N_OBJECTS = 20
OBJ_SIZE = 10240  #bytes

os.makedirs(OUT, exist_ok=True)
random.seed(42)  #same bytes every time

for i in range(1, N_OBJECTS + 1):
    with open(os.path.join(OUT, f"obj{i:02d}.dat"), "wb") as f:
        f.write(random.randbytes(OBJ_SIZE))

imgs = "\n".join(
    f'  <img src="obj{i:02d}.dat" alt="object {i}">' for i in range(1, N_OBJECTS + 1)
)
html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>CN Test Page</title></head>
<body>
<h1>CN Test Page</h1>
{imgs}
</body>
</html>
"""
with open(os.path.join(OUT, "index.html"), "w") as f:
    f.write(html)

print(f"Generated index.html and {N_OBJECTS} objects in {OUT}")
