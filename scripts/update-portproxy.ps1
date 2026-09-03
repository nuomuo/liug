# 更新 WSL 端口转发脚本
# 用法：以管理员身份运行 Windows PowerShell，执行本脚本
#   .\update-portproxy.ps1          # 默认转发 4300
#   .\update-portproxy.ps1 -Port 4301 -ListenPort 4300   # 转发其他端口

param(
    [int]$Port = 4300,        # WSL 内服务监听的端口（connectport）
    [int]$ListenPort = 0      # Windows 对外监听端口，0 表示与 $Port 相同
)
if ($ListenPort -eq 0) { $ListenPort = $Port }

# ---------- 检查管理员权限（未提权则自动以管理员重启自身） ----------
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "未以管理员运行，正在请求提权..." -ForegroundColor Yellow
    Start-Process powershell -Verb RunAs -ArgumentList "-ExecutionPolicy Bypass -File `"$PSCommandPath`" -Port $Port -ListenPort $ListenPort"
    exit 0
}

# ---------- 获取 WSL IP ----------
$wslIp = (wsl -e hostname -I).Trim().Split(' ')[0]
if (-not $wslIp) {
    Write-Host "错误：无法获取 WSL IP，请确认 WSL 正在运行" -ForegroundColor Red
    exit 1
}
Write-Host "WSL IP: $wslIp"

# ---------- 更新端口转发（先删旧规则再添加） ----------
netsh interface portproxy delete v4tov4 listenport=$ListenPort 2>$null | Out-Null
netsh interface portproxy add v4tov4 listenport=$ListenPort connectaddress=$wslIp connectport=$Port | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误：端口转发添加失败" -ForegroundColor Red
    exit 1
}
Write-Host "已转发: Windows:$ListenPort -> WSL(${wslIp}):$Port" -ForegroundColor Green

# ---------- 防火墙放行（已存在则跳过） ----------
$ruleName = "WSL Port $ListenPort"
if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort $ListenPort -Action Allow | Out-Null
    Write-Host "已添加防火墙规则: $ruleName" -ForegroundColor Green
} else {
    Write-Host "防火墙规则已存在: $ruleName"
}

# ---------- 输出当前结果 ----------
Write-Host "`n当前端口转发规则："
netsh interface portproxy show all

# ---------- 显示本机局域网 IP，供其他设备访问 ----------
Write-Host "`n本机局域网 IP（其他设备访问以下地址）："
Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -ne $wslIp } |
    Select-Object -ExpandProperty IPAddress

Write-Host "`n完成。请确认 WSL 内服务已监听 0.0.0.0:$Port"
Write-Host "验证: 先在本机 curl http://localhost:$ListenPort，再从局域网设备访问。"
