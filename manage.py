# -*- coding: utf-8 -*-
"""流光 LIUG 一键管理脚本

用法（Windows PowerShell / CMD 均可）：
    python manage.py build              # 编译前后端所有模块（Python 语法检查 + client + admin_client）
    python manage.py start              # 启动远程后端（4300 正式库）
    python manage.py stop               # 停止远程后端
    python manage.py restart            # 重启远程后端
    python manage.py status             # 查看端口/进程状态

    所有命令均可加 --test 使用测试环境（4301 端口 + data/users.test.db + data/users-test/），
    与正式库（4300）完全隔离：
        python manage.py start --test
        python manage.py restart --test
"""
import argparse
import compileall
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROD_PORT = 4300
TEST_PORT = 4301

CREATE_NEW_PROCESS_GROUP = 0x00000200
DETACHED_PROCESS = 0x00000008
CREATE_BREAKAWAY_FROM_JOB = 0x01000000


# ---------------------------------------------------------------- 端口 / 进程

def listening_pids(port):
    """返回占用指定端口处于 LISTENING 状态的进程 {pid: 进程名}。"""
    try:
        out = subprocess.run(
            ['netstat', '-ano', '-p', 'tcp'],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except Exception:
        return {}
    result = {}
    for line in out.splitlines():
        parts = line.split()
        # 协议  本地地址  外部地址  状态  PID
        if len(parts) >= 5 and parts[3] == 'LISTENING' and parts[1].endswith(f':{port}'):
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
    env['PYTHONIOENCODING'] = 'utf-8'
    if args.test:
        # 必须与启动命令放在同一次进程环境中，绝不依赖终端残留变量
        env['LIUG_USERS_DB_PATH'] = str(ROOT / 'data' / 'users.test.db')
        env['LIUG_USERS_DIR'] = str(ROOT / 'data' / 'users-test')
        env['PORT'] = str(TEST_PORT)

    log_path = ROOT / 'data' / ('server.test.log' if args.test else 'server.log')
    log_path.parent.mkdir(parents=True, exist_ok=True)

    print(f'[启动] {tag}环境后端：端口 {port}，日志 {log_path.relative_to(ROOT)}')
    base_flags = CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
    with open(log_path, 'w', encoding='utf-8') as log:
        popen_kwargs = dict(
            cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )
        try:
            # 优先脱离调用方所在的 Job Object，确保脚本退出（或所在终端会话结束）后服务仍存活
            proc = subprocess.Popen(
                [sys.executable, str(ROOT / 'server' / 'app.py')],
                creationflags=base_flags | CREATE_BREAKAWAY_FROM_JOB, **popen_kwargs,
            )
        except OSError:
            # 当前进程不在 Job 中或不允许脱离时，此标志会让 CreateProcess 失败，降级重试
            proc = subprocess.Popen(
                [sys.executable, str(ROOT / 'server' / 'app.py')],
                creationflags=base_flags, **popen_kwargs,
            )

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


def cmd_stop(args):
    port = TEST_PORT if args.test else PROD_PORT
    pids = listening_pids(port)
    if not pids:
        print(f'[空闲] 端口 {port} 没有服务在运行')
        return 0

    for pid, name in pids.items():
        if not name.lower().startswith('python'):
            # 桌面端 liug.exe 等也可能占用 4300，不能误杀
            print(f'[跳过] PID {pid}（{name}）不是 python 进程，请手动处理')
            continue
        print(f'[停止] 终止 {name} (PID {pid}) ...')
        subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True, timeout=10)

    if wait_port(port, expect_up=False, timeout=10):
        print(f'[成功] 端口 {port} 已释放')
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
        description='流光 LIUG 一键管理脚本（build/start/stop/restart/status）')
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

    args = parser.parse_args()
    sys.exit(args.fn(args))


if __name__ == '__main__':
    main()
