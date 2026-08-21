"""生成一个最小但完全合法的 PDF，用于验证附件预览功能（一次性脚本）。"""
import os

out = "/app/data/uploads/preview_test.pdf"
os.makedirs("/app/data/uploads", exist_ok=True)

body = b"BT /F1 24 Tf 72 720 Td (COO Preview Test - PDF preview works) Tj ET"
objs = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    b"<< /Length %d >>\nstream\n%s\nendstream" % (len(body), body),
    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
]

data = bytearray(b"%PDF-1.4\n")
offsets = []
for i, o in enumerate(objs, start=1):
    offsets.append(len(data))
    data += b"%d 0 obj\n" % i + o + b"\nendobj\n"
xref_pos = len(data)
data += b"xref\n0 6\n0000000000 65535 f \n"
for off in offsets:
    data += b"%010d 00000 n \n" % off
data += b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % xref_pos

with open(out, "wb") as f:
    f.write(bytes(data))
print("written", out, len(data), "bytes; header:", data[:8])
