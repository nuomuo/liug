const BASE = '';

// 401 时的全局回调（由 store.js 注册）：跳转回登录页
let onUnauthorized = null;
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

async function req(method, url, body) {
  const res = await fetch(BASE + url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    if (res.status === 401 && onUnauthorized && !url.startsWith('/api/auth/login')) {
      onUnauthorized();
    }
    const err = new Error('API ' + res.status);
    err.res = res;
    try {
      err.data = await res.json();
    } catch {}
    throw err;
  }
  return res.json();
}

export const api = {
  // 认证
  login: (username, password) => req('POST', '/api/auth/login', { username, password }),
  logout: () => req('POST', '/api/auth/logout'),
  me: () => req('GET', '/api/auth/me'),
  changePassword: (oldPassword, newPassword) =>
    req('POST', '/api/auth/change-password', { oldPassword, newPassword }),

  // 官方节假日安排（含调休），year 为年份
  getHolidays: (year) => req('GET', '/api/holidays?year=' + year),

  bootstrap: () => req('GET', '/api/bootstrap'),
  createTask: (task) => req('POST', '/api/tasks', task),
  updateTask: (id, patch) => req('PUT', `/api/tasks/${id}`, patch),
  deleteTask: (id) => req('DELETE', `/api/tasks/${id}`),
  createProject: (p) => req('POST', '/api/projects', p),
  updateProject: (id, patch) => req('PUT', `/api/projects/${id}`, patch),
  deleteProject: (id) => req('DELETE', `/api/projects/${id}`),
  search: (q) => req('GET', '/api/search?q=' + encodeURIComponent(q)),
  importCsv: (csvPath) => req('POST', '/api/import', { csvPath }),
  createCountdown: (c) => req('POST', '/api/countdowns', c),
  updateCountdown: (id, patch) => req('PUT', `/api/countdowns/${id}`, patch),
  deleteCountdown: (id) => req('DELETE', `/api/countdowns/${id}`),
};
