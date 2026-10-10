# -*- coding: utf-8 -*-
"""冻结模式（liug.exe）的数据目录管理。

数据目录固定为用户家目录下的 .liug（如 C:\\Users\\<用户>\\.liug）：
- 首次启动若发现 exe 同级的旧 data/ 目录，自动整体迁移到 .liug（本地数据、登录态、
  小组件窗口状态等全部随迁），迁移为一次性动作；
- 目录设置「隐藏 + 系统」属性（资源管理器默认不可见）；
- 通过 ACL 拒绝当前用户删除该目录本身（deny DE，仅目录对象、不继承），应用内部
  正常读写不受影响——防的是误删，用户仍是所有者，可自行用
  icacls "<目录>" /remove:d "<域>\\<用户>" 恢复删除权限。

开发模式（python desktop/main.py）不走本模块，仍用项目 data/ 目录。
"""
import ctypes
import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_DIR_NAME = '.liug'

_FILE_ATTRIBUTE_HIDDEN = 0x2
_FILE_ATTRIBUTE_SYSTEM = 0x4


def _say(msg):
    # console=False 冻结模式下 stdout 可能为 None
    try:
        print(f'[liug] {msg}')
    except Exception:
        pass


def _is_hidden(path: Path) -> bool:
    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    return attrs != 0xFFFFFFFF and bool(attrs & _FILE_ATTRIBUTE_HIDDEN)


def _protect_dir(path: Path):
    """隐藏 + 拒绝删除目录本身（幂等：已设置过则跳过）。"""
    if sys.platform != 'win32' or _is_hidden(path):
        return
    try:
        ctypes.windll.kernel32.SetFileAttributesW(
            str(path), _FILE_ATTRIBUTE_HIDDEN | _FILE_ATTRIBUTE_SYSTEM)
    except Exception:
        pass
    domain = os.environ.get('USERDOMAIN')
    user = os.environ.get('USERNAME')
    if not user:
        return
    account = f'{domain}\\{user}' if domain else user
    try:
        subprocess.run(
            ['icacls', str(path), '/deny', f'{account}:(DE)'],
            capture_output=True, timeout=15,
        )
    except Exception:
        pass


def _migrate_legacy_data(old_dir: Path, new_dir: Path):
    """exe 同级 data/ 有内容且 .liug 尚无数据 → 整体迁移（一次性）。"""
    try:
        has_old = old_dir.is_dir() and any(old_dir.iterdir())
        has_new = new_dir.is_dir() and any(new_dir.iterdir())
    except OSError:
        return
    if not has_old or has_new:
        return
    _say(f'检测到旧数据目录 {old_dir}，正在迁移到 {new_dir} ...')
    try:
        if not new_dir.exists():
            new_dir.parent.mkdir(parents=True, exist_ok=True)
            os.rename(old_dir, new_dir)      # 同盘原子迁移
        else:                                # new 存在但为空：逐项搬入
            new_dir.mkdir(parents=True, exist_ok=True)
            for item in list(old_dir.iterdir()):
                shutil.move(str(item), str(new_dir / item.name))
            old_dir.rmdir()
        _say('迁移完成')
    except OSError:
        # 跨盘 rename 失败等：退化为逐项复制搬移
        try:
            new_dir.mkdir(parents=True, exist_ok=True)
            for item in list(old_dir.iterdir()):
                shutil.move(str(item), str(new_dir / item.name))
            try:
                old_dir.rmdir()
            except OSError:
                pass
            _say('迁移完成（逐项搬移）')
        except Exception as e:
            _say(f'迁移失败（旧数据保留在 {old_dir}）：{e}')


def init_frozen_paths(exe_dir: Path, home: Path = None):
    """冻结模式入口调用：确定 ~/.liug、迁移旧 data、防删保护。返回数据目录。"""
    data_dir = (home or Path.home()) / APP_DIR_NAME
    _migrate_legacy_data(exe_dir / 'data', data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    _protect_dir(data_dir)
    return data_dir
