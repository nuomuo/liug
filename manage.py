# -*- coding: utf-8 -*-
"""流光 LIUG 一键管理脚本（Windows / Linux 通用）

用法：
    python manage.py build              # 编译前后端所有模块（Python 语法检查 + client + admin_client）
    python manage.py start              # 启动远程后端（4300 正式库，后台常驻）
    python manage.py stop               # 停止远程后端
    python manage.py restart            # 重启远程后端
    python manage.py status             # 查看端口/进程状态
    python manage.py pack                # 打包桌面版（版本号取 config.yaml → web/release/liug-v<版本>.exe，并同步官网版本号）

    所有命令均可加 --test 使用测试环境（4301 端口 + data/users.test.db + data/users-test/），
    与正式库（4300）完全隔离：
        python manage.py start --test
        python manage.py restart --test

    Linux（服务器部署）：服务以 setsid 方式后台启动，SSH 断开后仍存活；
    stop 先发 SIGTERM 优雅退出，超时再 SIGKILL 强制终止。

    服务环境变量可在根目录 config.yaml 的 env 段配置（如管理端 IP 白名单
    LIUG_ADMIN_ALLOWED_IPS），start / restart 时自动读取并注入，修改后 restart 即生效。
"""
import argparse
import compileall
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROD_PORT = 4300
TEST_PORT = 4301

IS_WINDOWS = os.name == 'nt'

if IS_WINDOWS:
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    DETACHED_PROCESS = 0x00000008
    CREATE_BREAKAWAY_FROM_JOB = 0x01000000


# ---------------------------------------------------------------- 端口 / 进程

def _local_port(addr):
    """'0.0.0.0:4300' / '[::]:4300' / ':::4300' / '*:4300' → 4300；解析失败返回 None。"""
    if addr.startswith('['):
        addr = addr.split(']')[-1]
    if ':' not in addr:
        return None
    try:
        return int(addr.rsplit(':', 1)[1])
    except ValueError:
        return None


def _pids_ss(port):
    """ss -tlnp：现代 Linux 标配（iproute2），一行同时给出端口与 PID。"""
    out = subprocess.run(
        ['ss', '-tlnpH'], capture_output=True, text=True, timeout=10,
    ).stdout
    result = {}
    occupied = False
    for line in out.splitlines():
        parts = line.split()
        # 状态 Recv-Q Send-Q  本地地址  对端地址  [users:(("name",pid=123,fd=6),...)]
        if len(parts) < 4 or parts[0] != 'LISTEN' or _local_port(parts[3]) != port:
            continue
        occupied = True
        for name, pid in re.findall(r'users:\(\("([^"]+)",pid=(\d+)', line):
            pid = int(pid)
            if pid > 0:
                result[pid] = name
    if occupied and not result:
        result[0] = '?'   # 端口被占但拿不到 PID（非 root 看他人进程时），用哨兵 pid=0 表示
    return result


def _pids_netstat_linux(port):
    """netstat -tlnp：无 ss 的老系统回退（net-tools）。"""
    out = subprocess.run(
        ['netstat', '-tlnp'], capture_output=True, text=True, timeout=10,
    ).stdout
    result = {}
    occupied = False
    for line in out.splitlines():
        parts = line.split()
        # 协议 Recv-Q Send-Q 本地地址 对端地址 状态 [PID/名称]
        if len(parts) < 6 or not parts[0].startswith('tcp'):
            continue
        if parts[5] != 'LISTEN' or _local_port(parts[3]) != port:
            continue
        occupied = True
        if len(parts) >= 7 and '/' in parts[6]:
            pid_s, name = parts[6].rsplit('/', 1)
            if pid_s.isdigit() and int(pid_s) > 0:
                result[int(pid_s)] = name
    if occupied and not result:
        result[0] = '?'
    return result


def _pids_netstat_windows(port):
    out = subprocess.run(
        ['netstat', '-ano', '-p', 'tcp'],
        capture_output=True, text=True, timeout=10,
    ).stdout
    result = {}
    for line in out.splitlines():
        parts = line.split()
        # 协议  本地地址  外部地址  状态  PID
        if len(parts) >= 5 and parts[3] == 'LISTENING' and _local_port(parts[1]) == port:
            pid = int(parts[4])
            if pid <= 0:
                continue
            try:
                info = subprocess.run(
                    ['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'],
                    capture_output=True, text=True, timeout=10,
                ).stdout.strip()
                name = info.split('","')[0].strip('"') if info else '?'
            except Exception:
                name = '?'
            result[pid] = name
    return result


def listening_pids(port):
    """返回占用指定端口处于监听状态的进程 {pid: 进程名}（pid=0 表示被占但 PID 未知）。"""
    if IS_WINDOWS:
        try:
            return _pids_netstat_windows(port)
        except Exception:
            return {}
    for probe in (_pids_ss, _pids_netstat_linux):
        try:
            return probe(port)
        except Exception:
            continue
    return {}


def wait_port(port, expect_up, timeout=15):
    """轮询等待端口监听（expect_up=True）或释放（expect_up=False）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        up = bool(listening_pids(port))
        if up == expect_up:
            return True
        time.sleep(0.5)
    return False


# ---------------------------------------------------------------- build

def npm_build(prefix, label):
    """对指定前端目录执行 npm install（仅缺 node_modules 时）+ npm run build。"""
    npm = shutil.which('npm')
    if not npm:
        print(f'[失败] {label}：未找到 npm，请先安装 Node.js')
        return False
    pkg = ROOT / prefix
    if not (pkg / 'package.json').exists():
        print(f'[跳过] {label}：未找到 {prefix}/package.json')
        return True
    if not (pkg / 'node_modules').exists():
        print(f'[安装] {label}：node_modules 缺失，执行 npm install ...')
        r = subprocess.call([npm, 'install', '--prefix', str(pkg)], cwd=str(ROOT))
        if r != 0:
            print(f'[失败] {label} npm install 退出码 {r}')
            return False
    print(f'[构建] {label}：npm run build ...')
    r = subprocess.call([npm, 'run', 'build', '--prefix', str(pkg)], cwd=str(ROOT))
    if r != 0:
        print(f'[失败] {label} npm run build 退出码 {r}')
        return False
    print(f'[完成] {label}')
    return True


def cmd_build(_args):
    print('[1/3] Python 语法检查（core + server）...')
    ok = compileall.compile_dir(str(ROOT / 'core'), quiet=1) and \
        compileall.compile_dir(str(ROOT / 'server'), quiet=1)
    if not ok:
        print('[失败] Python 语法检查未通过')
        return 1
    print('[完成] Python 语法检查')
    if not npm_build('client', '[2/3] 主应用前端 client'):
        return 1
    if not npm_build('admin_client', '[3/3] 管理端前端 admin_client'):
        return 1
    print('全部模块编译完成。')
    return 0


# ---------------------------------------------------------------- pack（打包发布）

def cmd_pack(_args):
    """打包桌面版：PyInstaller 打包 liug.exe → web/release/liug-v<版本>.exe，并同步官网版本号。"""
    version = load_version()
    if not version:
        print('[失败] config.yaml 未配置版本号：请在顶层添加  version: "x.y"（如 version: "1.0"）后重试')
        return 1
    print(f'[版本] config.yaml version = {version}')

    # exe 内嵌 client/dist 静态资源，必须先构建主应用前端
    if not npm_build('client', '[1/4] 主应用前端 client（打包内嵌）'):
        return 1

    if subprocess.run([sys.executable, '-m', 'PyInstaller', '--version'],
                      capture_output=True).returncode != 0:
        print('[失败] 未找到 PyInstaller，请先安装：pip install pyinstaller')
        return 1

    print('[2/4] PyInstaller 打包（liug.spec）...')
    if subprocess.call([sys.executable, '-m', 'PyInstaller', '--noconfirm', str(ROOT / 'liug.spec')],
                       cwd=str(ROOT)) != 0:
        print('[失败] PyInstaller 打包失败')
        return 1
    exe_path = ROOT / 'dist' / 'liug.exe'
    if not exe_path.exists():
        print(f'[失败] 未找到打包产物：{exe_path.relative_to(ROOT)}')
        return 1

    release_dir = ROOT / 'web' / 'release'
    release_dir.mkdir(parents=True, exist_ok=True)
    release_path = release_dir / f'liug-v{version}.exe'
    shutil.copy2(exe_path, release_path)
    size_mb = release_path.stat().st_size / 1024 / 1024
    print(f'[3/4] 发布产物：{release_path.relative_to(ROOT)}（{size_mb:.1f} MB）')

    # 同步官网版本号：v x.y 形式的版本号全量替换（lambda 替换，避免版本串中的反斜杠被当作组引用）
    index_path = ROOT / 'web' / 'index.html'
    try:
        html = index_path.read_text(encoding='utf-8')
    except OSError:
        print(f'[跳过] 未找到官网页面：{index_path.relative_to(ROOT)}')
        html = ''
    new_html, count = re.subn(r'v\d+(?:\.\d+)+', lambda m: f'v{version}', html)
    if count:
        index_path.write_text(new_html, encoding='utf-8')
        print(f'[4/4] 官网版本号已同步：替换 {count} 处 → v{version}')
    else:
        print(f'[4/4] 官网版本号无需同步（目标 v{version}）')

    print('打包发布完成。')
    return 0


# ---------------------------------------------------------------- 配置文件

CONFIG_FILE = ROOT / 'config.yaml'


def _parse_env_section(text):
    """无 PyYAML 时的简易解析：仅支持顶层 env: 段下缩进的 KEY: value（# 注释、可选引号）。"""
    result = {}
    in_env = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if not raw[0].isspace():          # 顶层键
            in_env = stripped == 'env:'
            continue
        if not in_env or ':' not in stripped:
            continue
        key, _, value = stripped.partition(':')
        key, value = key.strip(), value.strip()
        # 去掉行内注释（# 前有空白才算，避免误伤值中的 #）
        for i, ch in enumerate(value):
            if ch == '#' and i > 0 and value[i - 1].isspace():
                value = value[:i].rstrip()
                break
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key and value:
            result[key] = value
    return result


def load_env_config(path=CONFIG_FILE):
    """读取 config.yaml 的 env 段 → {环境变量名: 字符串值}；文件不存在或格式异常返回 {}。"""
    try:
        text = path.read_text(encoding='utf-8')
    except OSError:
        return {}
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text) or {}
    except ImportError:
        data = _parse_env_section(text)
    if not isinstance(data, dict):
        return {}
    env_map = data.get('env') or {}
    if not isinstance(env_map, dict):
        return {}
    # YAML 可能解析出 int/bool 等标量，统一转字符串
    return {str(k): str(v) for k, v in env_map.items() if k and v is not None}


def load_version(path=None):
    """读取 config.yaml 顶层 version 键 → 版本号字符串；文件不存在/未配置/值为空返回 None。"""
    if path is None:
        # 默认值在调用时才取 CONFIG_FILE（而非定义时绑定），便于运行中替换配置路径
        path = CONFIG_FILE
    try:
        text = path.read_text(encoding='utf-8')
    except OSError:
        return None
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            return None
        value = data.get('version')
    except ImportError:
        # 无 PyYAML 的简易解析：仅识别顶层 version: value（# 注释、可选引号）
        value = None
        for raw in text.splitlines():
            stripped = raw.strip()
            if not stripped or stripped.startswith('#'):
                continue
            if raw[0].isspace():          # 跳过子级缩进行（version 必须是顶层键）
                continue
            if not stripped.startswith('version:'):
                continue
            value = stripped.partition(':')[2].strip()
            # 去掉行内注释（# 前有空白才算，避免误伤值中的 #）
            for i, ch in enumerate(value):
                if ch == '#' and i > 0 and value[i - 1].isspace():
                    value = value[:i].rstrip()
                    break
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            break
    if value is None:
        return None
    # YAML 可能解析出 int/float 等标量，统一转字符串
    return str(value).strip() or None


# ---------------------------------------------------------------- start / stop

def cmd_start(args):
    port = TEST_PORT if args.test else PROD_PORT
    tag = '测试' if args.test else '正式'

    pids = listening_pids(port)
    if pids:
        for pid, name in pids.items():
            print(f'[占用] 端口 {port} 已被 {name} (PID {pid}) 监听')
        print(f'如需重启请执行：python manage.py restart{" --test" if args.test else ""}')
        return 1

    env = os.environ.copy()
    # config.yaml 的 env 段：配置文件优先于 shell 遗留变量（配置文件即唯一真相源）
    env_overrides = load_env_config()
    if env_overrides.pop('PORT', None) is not None:
        print('[警告] config.yaml 中的 PORT 已忽略：端口由 manage.py 统一管理（默认 4300，--test 为 4301）')
    if env_overrides:
        print(f'[配置] 从 config.yaml 注入 {len(env_overrides)} 个环境变量：')
        for key, value in env_overrides.items():
            print(f'    {key}={value}')
            env[key] = value
    env['PYTHONIOENCODING'] = 'utf-8'
    if args.test:
        # 必须与启动命令放在同一次进程环境中，绝不依赖终端残留变量；
        # --test 的三个变量最后强制覆盖，防止 config.yaml 把测试环境指向正式库
        env['LIUG_USERS_DB_PATH'] = str(ROOT / 'data' / 'users.test.db')
        env['LIUG_USERS_DIR'] = str(ROOT / 'data' / 'users-test')
        env['PORT'] = str(TEST_PORT)

    log_path = ROOT / 'data' / ('server.test.log' if args.test else 'server.log')
    log_path.parent.mkdir(parents=True, exist_ok=True)

    print(f'[启动] {tag}环境后端：端口 {port}，日志 {log_path.relative_to(ROOT)}')
    argv = [sys.executable, str(ROOT / 'server' / 'app.py')]
    with open(log_path, 'w', encoding='utf-8') as log:
        popen_kwargs = dict(
            cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )
        if IS_WINDOWS:
            base_flags = CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
            try:
                # 优先脱离调用方所在的 Job Object，确保脚本退出（或所在终端会话结束）后服务仍存活
                proc = subprocess.Popen(
                    argv, creationflags=base_flags | CREATE_BREAKAWAY_FROM_JOB, **popen_kwargs,
                )
            except OSError:
                # 当前进程不在 Job 中或不允许脱离时，此标志会让 CreateProcess 失败，降级重试
                proc = subprocess.Popen(argv, creationflags=base_flags, **popen_kwargs)
        else:
            # setsid：脱离终端会话，SSH 断开后服务仍存活
            proc = subprocess.Popen(argv, start_new_session=True, **popen_kwargs)

    if not wait_port(port, expect_up=True, timeout=15):
        print(f'[失败] 端口 {port} 未在 15 秒内进入监听状态，最近日志：')
        try:
            tail = log_path.read_text(encoding='utf-8', errors='replace').splitlines()[-15:]
            for line in tail:
                print(f'    {line}')
        except OSError:
            print('    （无法读取日志）')
        return 1

    pids = listening_pids(port)
    pid = next(iter(pids), proc.pid)
    print(f'[成功] 服务已启动：PID {pid}')
    print(f'    主应用    http://localhost:{port}/')
    print(f'    管理端    http://localhost:{port}/admin/')
    return 0


def _kill(pid, force=False):
    """终止进程：Windows 用 taskkill /F；Linux 先 SIGTERM（force 时 SIGKILL）。"""
    if IS_WINDOWS:
        subprocess.run(['taskkill', '/F', '/PID', str(pid)],
                       capture_output=True, timeout=10)
    else:
        try:
            os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass


def cmd_stop(args):
    port = TEST_PORT if args.test else PROD_PORT
    pids = listening_pids(port)
    if not pids:
        print(f'[空闲] 端口 {port} 没有服务在运行')
        return 0

    targets = {}
    for pid, name in pids.items():
        if pid <= 0:
            print('[占用] 端口被监听但无法获取进程 PID（可能需要 root/sudo 权限）')
            continue
        if not name.lower().startswith('python'):
            # 桌面端 liug.exe 等也可能占用 4300，不能误杀
            print(f'[跳过] PID {pid}（{name}）不是 python 进程，请手动处理')
            continue
        targets[pid] = name

    if not targets:
        print('[未处理] 没有可终止的 python 进程')
        return 1

    for pid, name in targets.items():
        print(f'[停止] 终止 {name} (PID {pid}) ...')
        _kill(pid, force=IS_WINDOWS)   # Windows taskkill /F 本身就是强杀

    if wait_port(port, expect_up=False, timeout=10):
        print(f'[成功] 端口 {port} 已释放')
        return 0

    if not IS_WINDOWS:
        # SIGTERM 未及时生效（进程卡死等），升级 SIGKILL 强制终止
        print('[等待] 优雅退出超时，强制终止 ...')
        for pid in targets:
            _kill(pid, force=True)
        if wait_port(port, expect_up=False, timeout=5):
            print(f'[成功] 端口 {port} 已释放（强制终止）')
            return 0

    print(f'[警告] 端口 {port} 仍被占用：{listening_pids(port)}')
    return 1


def cmd_restart(args):
    cmd_stop(args)
    time.sleep(1)
    return cmd_start(args)


def cmd_status(args):
    port = TEST_PORT if args.test else PROD_PORT
    pids = listening_pids(port)
    if pids:
        for pid, name in pids.items():
            if pid <= 0:
                print(f'[占用] 端口 {port} 被监听，但无法获取进程信息（可能需要 root/sudo）')
            else:
                print(f'[运行中] 端口 {port}：{name} (PID {pid})')
        return 0
    print(f'[未运行] 端口 {port} 无服务监听')
    return 1


# ---------------------------------------------------------------- 入口

def main():
    # 行缓冲，保证脚本提示按实际顺序先于 npm 输出显示
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description='流光 LIUG 一键管理脚本（build/start/stop/restart/status/pack）')
    sub = parser.add_subparsers(dest='command', required=True)

    for name, fn, help_ in [
        ('build', cmd_build, '编译前后端所有模块'),
        ('start', cmd_start, '启动远程后端'),
        ('stop', cmd_stop, '停止远程后端'),
        ('restart', cmd_restart, '重启远程后端'),
        ('status', cmd_status, '查看端口/进程状态'),
    ]:
        p = sub.add_parser(name, help=help_)
        p.add_argument('--test', action='store_true',
                       help='使用测试环境（4301 + data/users.test.db + data/users-test/）')
        p.set_defaults(fn=fn)

    # pack 打包的是桌面版 exe，与正式/测试环境无关，单独注册（不带 --test 参数）
    p = sub.add_parser('pack', help='打包桌面版发布产物到 web/release/（版本号取 config.yaml 的 version）')
    p.set_defaults(fn=cmd_pack)

    args = parser.parse_args()
    sys.exit(args.fn(args))


if __name__ == '__main__':
    main()
