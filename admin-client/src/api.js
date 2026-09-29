/* 系统管理前端的 /system/* API 封装（与后端 FastAPI routes_system.py 对接） */
export async function api(method, path, body) {
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
