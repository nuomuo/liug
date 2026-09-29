/* 系统管理独立前端逻辑（前后端分离：仅通过 /system/* API 与后端通信） */

let me = null; // 当前登录的管理员

// ---------- API 封装 ----------
async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = null;
  try {
    data = await res.json();
  } catch {}
  if (!res.ok) {
    const err = new Error((data && data.error) || '请求失败');
    err.status = res.status;
    throw err;
  }
  return data;
}

// ---------- 视图切换 ----------
function show(view) {
  document.getElementById('login-view').classList.toggle('hidden', view !== 'login');
  document.getElementById('admin-view').classList.toggle('hidden', view !== 'admin');
}

function toast(msg, isError) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.toggle('error', !!isError);
  el.classList.remove('hidden');
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add('hidden'), 2600);
}

// ---------- 登录 / 退出 ----------
async function login() {
  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value;
  const errEl = document.getElementById('login-error');
  errEl.textContent = '';
  try {
    const data = await api('POST', '/system/auth/login', { username, password });
    me = data.user;
    enterAdmin();
  } catch (e) {
    errEl.textContent = e.message;
  }
}

async function logout() {
  try {
    await api('POST', '/system/auth/logout');
  } catch {}
  me = null;
  show('login');
}

function enterAdmin() {
  document.getElementById('login-password').value = '';
  document.getElementById('me-name').textContent = me.username;
  show('admin');
  loadUsers();
}

// ---------- 用户列表 ----------
async function loadUsers() {
  try {
    const data = await api('GET', '/system/users');
    renderUsers(data.users);
  } catch (e) {
    if (e.status === 401 || e.status === 403) {
      me = null;
      show('login');
    }
    toast(e.message, true);
  }
}

function renderUsers(users) {
  document.getElementById('user-count').textContent = users.length ? `${users.length} 个账户` : '';
  const tbody = document.querySelector('#user-table tbody');
  tbody.innerHTML = '';
  document.getElementById('empty-tip').classList.toggle('hidden', users.length > 0);
  for (const u of users) {
    const tr = document.createElement('tr');
    if (u.disabled) tr.className = 'off';
    const isMe = me && u.id === me.id;
    tr.innerHTML = `
      <td class="td-name">${escapeHtml(u.username)}${isMe ? '<span class="me-tag">当前账户</span>' : ''}</td>
      <td><span class="role-tag ${u.role}">${u.role === 'admin' ? '管理员' : '普通用户'}</span></td>
      <td><span class="status-dot ${u.disabled ? 'off' : 'on'}"></span>${u.disabled ? '已禁用' : '正常'}</td>
      <td class="td-time">${fmtTime(u.createdAt)}</td>
      <td class="td-actions">
        <button class="btn" onclick="openReset('${u.id}', '${escapeHtml(u.username)}')">重置密码</button>
        <button class="btn" onclick="toggleRole('${u.id}', '${u.role}')">${u.role === 'admin' ? '降为普通用户' : '设为管理员'}</button>
        <button class="btn" onclick="toggleDisabled('${u.id}', ${u.disabled})">${u.disabled ? '启用' : '禁用'}</button>
        <button class="btn danger" onclick="removeUser('${u.id}', '${escapeHtml(u.username)}')">删除</button>
      </td>`;
    tbody.appendChild(tr);
  }
}

// ---------- 用户操作 ----------
function openCreate() {
  document.getElementById('new-username').value = '';
  document.getElementById('new-password').value = '';
  document.getElementById('new-role').value = 'user';
  document.getElementById('create-btn').disabled = false;
  document.getElementById('create-modal').classList.remove('hidden');
}
function closeCreate() {
  document.getElementById('create-modal').classList.add('hidden');
}

async function createUser() {
  const payload = {
    username: document.getElementById('new-username').value.trim(),
    password: document.getElementById('new-password').value,
    role: document.getElementById('new-role').value,
  };
  const btn = document.getElementById('create-btn');
  btn.disabled = true;
  try {
    await api('POST', '/system/users', payload);
    toast(`用户 ${payload.username} 创建成功`);
    closeCreate();
    await loadUsers();
  } catch (e) {
    toast(e.message, true);
    btn.disabled = false;
  }
}

function openReset(id, name) {
  resetTarget = id;
  document.getElementById('reset-name').textContent = name;
  document.getElementById('reset-password').value = '';
  document.getElementById('reset-modal').classList.remove('hidden');
}
function closeReset() {
  document.getElementById('reset-modal').classList.add('hidden');
}
let resetTarget = null;

async function submitReset() {
  const password = document.getElementById('reset-password').value;
  if (!password || password.length < 6) {
    toast('新密码至少需要 6 个字符', true);
    return;
  }
  try {
    const data = await api('PUT', `/system/users/${resetTarget}`, { password });
    toast(`已重置 ${data.user.username} 的密码`);
    closeReset();
  } catch (e) {
    toast(e.message, true);
  }
}

async function toggleRole(id, role) {
  try {
    await api('PUT', `/system/users/${id}`, { role: role === 'admin' ? 'user' : 'admin' });
    // 当前管理员自己被降级时，回到登录页
    if (me && id === me.id && role === 'admin') {
      toast('当前账户已降为普通用户');
      me = null;
      show('login');
      return;
    }
    await loadUsers();
  } catch (e) {
    toast(e.message, true);
  }
}

async function toggleDisabled(id, disabled) {
  try {
    await api('PUT', `/system/users/${id}`, { disabled: !disabled });
    if (me && id === me.id && !disabled) {
      toast('当前账户已被禁用');
      me = null;
      show('login');
      return;
    }
    await loadUsers();
  } catch (e) {
    toast(e.message, true);
  }
}

async function removeUser(id, name) {
  if (!confirm(`确定删除用户「${name}」？该用户的所有数据（清单/任务/倒数日）将被永久删除，且无法恢复。`)) return;
  try {
    await api('DELETE', `/system/users/${id}`);
    toast(`用户 ${name} 已删除`);
    await loadUsers();
  } catch (e) {
    toast(e.message, true);
  }
}

// ---------- 工具 ----------
function fmtTime(iso) {
  return iso ? String(iso).slice(0, 19).replace('T', ' ') : '-';
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[c]);
}

// 登录框内回车提交
document.getElementById('login-password').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') login();
});
document.getElementById('login-username').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') login();
});

// 启动：已登录则直接进入管理页
(async () => {
  try {
    const data = await api('GET', '/system/auth/me');
    me = data.user;
    enterAdmin();
  } catch {
    show('login');
  }
})();
