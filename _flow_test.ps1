$ErrorActionPreference = 'Continue'
$BASE = 'http://localhost:8000/api'
$PASS = 0; $FAIL = 0
function Chk($name, $cond, $extra = '') {
  if ($cond) { $script:PASS++; Write-Host "  PASS  $name $extra" -ForegroundColor Green }
  else { $script:FAIL++; Write-Host "  FAIL  $name $extra" -ForegroundColor Red }
}
function Login($u, $p) {
  $b = @{username = $u; password = $p } | ConvertTo-Json
  $r = Invoke-RestMethod -Uri "$BASE/auth/login" -Method Post -ContentType 'application/json' -Body $b
  return $r.access_token
}

# ---------- 准备测试文件 ----------
$tmp = Join-Path $env:TEMP 'coo_test'
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$txtFile = Join-Path $tmp 'coo_test_notes.txt'
$pdfFile = Join-Path $tmp 'coo_test_doc.pdf'
Set-Content -Path $txtFile -Value 'COO test note 001 - RMA original certificate' -Encoding UTF8
# 极简合法 PDF（含 %PDF 头，mime 会按 .pdf 识别）
$pdfSrc = "%PDF-1.4`n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj`n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj`n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj`ntrailer<</Root 1 0 R>>`n%%EOF"
$pdfBytes = [System.Text.Encoding]::ASCII.GetBytes($pdfSrc)
[IO.File]::WriteAllBytes($pdfFile, $pdfBytes)

# ---------- 1. 订单流程 ----------
Write-Host '== ORDER FLOW =='
$admin = Login 'admin' 'admin123'
$ah = @{ Authorization = "Bearer $admin" }

# 取一个订单
$order = (Invoke-RestMethod -Uri "$BASE/orders" -Headers $ah)[0]
$oid = $order.id
Write-Host "order id=$oid no=$($order.order_no)"

# 取一个资料包（COO-01）
$pkg = (Invoke-RestMethod -Uri "$BASE/packages" -Headers $ah | Where-Object { $_.code -eq 'COO-01' })[0]
$pid = $pkg.id

# 若订单还没有该资料包实例，则添加
$detail = Invoke-RestMethod -Uri "$BASE/orders/$oid" -Headers $ah
$op = $detail.packages | Where-Object { $_.package_id -eq $pid } | Select-Object -First 1
if (-not $op) {
  $op = Invoke-RestMethod -Uri "$BASE/orders/$oid/packages" -Method Post -Headers $ah -ContentType 'application/json' -Body (@{ package_id = $pid } | ConvertTo-Json)
  Write-Host "  created op id=$($op.id)"
} else {
  Write-Host "  reused op id=$($op.id)"
}
$opid = $op.id

# 上传附件（txt + pdf）
$form = @{
  files = Get-Item $txtFile, $pdfFile
  batch_no = 'TEST-B1'
}
$atts = Invoke-RestMethod -Uri "$BASE/orders/$oid/packages/$opid/attachments" -Method Post -Headers $ah -Form $form
Write-Host "uploaded attachments: $($atts.Count)"
Chk 'upload returns attachments' ($atts.Count -eq 2)
$txtAtt = $atts | Where-Object { $_.original_name -like '*.txt' } | Select-Object -First 1
$pdfAtt = $atts | Where-Object { $_.original_name -like '*.pdf' } | Select-Object -First 1

# 下载（带 token）
$down = Invoke-WebRequest -Uri "$BASE/orders/$oid/packages/$opid/attachments/$($txtAtt.id)/file" -Headers $ah
Chk 'download txt with token 200' ($down.StatusCode -eq 200)
Chk 'download content matches' ($down.Content -like '*COO test note*')

# 预览（带 token，pdf）
$prev = Invoke-WebRequest -Uri "$BASE/orders/$oid/packages/$opid/attachments/$($pdfAtt.id)/file?preview=true" -Headers $ah
Chk 'preview pdf 200' ($prev.StatusCode -eq 200)
Chk 'preview mime is pdf' ($prev.Headers['Content-Type'] -like '*pdf*')

# 导出 CSV（带 token）
$csv = Invoke-WebRequest -Uri "$BASE/orders/$oid/export" -Headers $ah
Chk 'export csv with token 200' ($csv.StatusCode -eq 200)
Chk 'export csv has BOM+header' ($csv.Content -like '*工厂*')

# 导出 CSV（不带 token）-> 预期 401，证明旧前端 window.location.href 会失败
$noAuthStatus = $null
try { Invoke-WebRequest -Uri "$BASE/orders/$oid/export" -ErrorAction Stop | Out-Null; $noAuthStatus = 200 }
catch { $noAuthStatus = $_.Exception.Response.StatusCode.value__ }
Chk 'export csv WITHOUT token -> 401 (old frontend bug reproduced)' ($noAuthStatus -eq 401)

# 导出 ZIP（带 token）
$zip = Invoke-WebRequest -Uri "$BASE/orders/$oid/export/zip" -Headers $ah
Chk 'export zip with token 200' ($zip.StatusCode -eq 200)
Chk 'zip is application/zip' ($zip.Headers['Content-Type'] -like '*zip*')

# 提交 + 两级审核闭环
$op = Invoke-RestMethod -Uri "$BASE/orders/$oid/packages/$opid/submit" -Method Post -Headers $ah
Chk 'order submit -> pending_dept' ($op.status -eq 'pending_dept')

$dept = Login 'dept_eng' 'dept123'
$dh = @{ Authorization = "Bearer $dept" }
$op = Invoke-RestMethod -Uri "$BASE/orders/$oid/packages/$opid/review" -Method Post -Headers $dh -ContentType 'application/json' -Body (@{ decision='approve'; level='dept'; reason='ok' } | ConvertTo-Json)
Chk 'dept approve -> pending_coo' ($op.status -eq 'pending_coo')

$coo = Login 'coo' 'coo123'
$ch = @{ Authorization = "Bearer $coo" }
$op = Invoke-RestMethod -Uri "$BASE/orders/$oid/packages/$opid/review" -Method Post -Headers $ch -ContentType 'application/json' -Body (@{ decision='approve'; level='coo'; reason='ok' } | ConvertTo-Json)
Chk 'coo approve -> released+locked' ($op.status -eq 'released' -and $op.locked -eq $true)

# 已放行不可改/不可移除
$delCode = $null
try { Invoke-RestMethod -Uri "$BASE/orders/$oid/packages/$opid" -Method Delete -Headers $ah -ErrorAction Stop | Out-Null; $delCode = 200 }
catch { $delCode = $_.Exception.Response.StatusCode.value__ }
Chk 'released op cannot be removed (400/4xx)' ($delCode -ge 400)

# ---------- 2. NAS 同步 ----------
Write-Host '== NAS SYNC =='
$sync = Invoke-RestMethod -Uri "$BASE/nas/sync" -Method Post -Headers $ch
Chk 'nas sync runs' ($sync.status -eq 'success' -or $sync.status -eq 'partial')
$stat = Invoke-RestMethod -Uri "$BASE/nas/status" -Headers $ah
Chk 'nas reachable' ($stat.nas_reachable -eq $true)
$reDet = Invoke-RestMethod -Uri "$BASE/orders/$oid" -Headers $ah
$attNow = ($reDet.packages | Where-Object { $_.id -eq $opid }).attachments
$syncedAll = -not ($attNow | Where-Object { $_.nas_synced -ne $true })
Chk 'order attachments synced to NAS' $syncedAll

# ---------- 3. 资料包流程 ----------
Write-Host '== PACKAGE FLOW =='
# 用提交人账号操作其负责包不可靠（种子包无 owner），改用 admin 全程
$ver = Invoke-RestMethod -Uri "$BASE/packages/$pid/versions" -Method Post -Headers $ah -ContentType 'application/json' -Body (@{ change_note='test' } | ConvertTo-Json)
Chk 'create version V1.0' ($ver.version_no -eq 'V1.0' -and $ver.status -eq 'draft')
$vid = $ver.id
$pform = @{ files = Get-Item $pdfFile; order_no='ORD-T'; batch_no='B1' }
$patts = Invoke-RestMethod -Uri "$BASE/packages/$pid/versions/$vid/attachments" -Method Post -Headers $ah -Form $pform
Chk 'package upload attachments' ($patts.Count -eq 1)
$v = Invoke-RestMethod -Uri "$BASE/packages/$pid/versions/$vid/submit" -Method Post -Headers $ah
Chk 'package submit -> pending_dept' ($v.status -eq 'pending_dept')
$v = Invoke-RestMethod -Uri "$BASE/packages/$pid/versions/$vid/review" -Method Post -Headers $dh -ContentType 'application/json' -Body (@{ decision='approve'; level='dept'; reason='ok' } | ConvertTo-Json)
Chk 'package dept approve -> pending_coo' ($v.status -eq 'pending_coo')
$v = Invoke-RestMethod -Uri "$BASE/packages/$pid/versions/$vid/review" -Method Post -Headers $ch -ContentType 'application/json' -Body (@{ decision='approve'; level='coo'; reason='ok' } | ConvertTo-Json)
Chk 'package coo approve -> released' ($v.status -eq 'released' -and $v.locked -eq $true)

# 受控区可见
$ctl = Invoke-RestMethod -Uri "$BASE/controlled" -Headers $ah
Chk 'controlled shows released package' (($ctl | Where-Object { $_.package_code -eq 'COO-01' -and $_.version.id -eq $vid }).Count -gt 0)

# 受控区 ZIP 下载
$czip = Invoke-WebRequest -Uri "$BASE/controlled/$pid/versions/$vid/export/zip" -Headers $ah
Chk 'controlled zip download 200' ($czip.StatusCode -eq 200)

# ---------- 4. 角色隔离复核 ----------
Write-Host '== ROLE ISOLATION =='
$aud = Login 'auditor' 'audit123'
try { Invoke-RestMethod -Uri "$BASE/nas/sync" -Method Post -Headers @{ Authorization = "Bearer $aud" } -ErrorAction Stop | Out-Null; $s2 = 200 } catch { $s2 = $_.Exception.Response.StatusCode.value__ }
Chk 'auditor cannot trigger NAS sync (403)' ($s2 -eq 403)

Write-Host ''
Write-Host "RESULT: PASS=$PASS FAIL=$FAIL"
