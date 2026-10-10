// 管理端 API（/admin 前缀；开发模式由 vite 代理到 4300，生产同源直连）
async function req(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
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
  login: (username, password) => req('POST', '/admin/login', { username, password }),
  logout: () => req('POST', '/admin/logout'),
  me: () => req('GET', '/admin/me'),

  listUsers: () => req('GET', '/admin/users'),
  createUser: (payload) => req('POST', '/admin/users', payload),
  updateUser: (id, patch) => req('PATCH', `/admin/users/${id}`, patch),
  deleteUser: (id) => req('DELETE', `/admin/users/${id}`),
};
