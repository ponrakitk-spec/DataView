export const jobIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
export class WorkerError extends Error {
  constructor(message: string, public status = 502) { super(message); }
}
export function connection(request: Request) {
  const origin = request.headers.get("origin");
  if (origin && origin !== new URL(request.url).origin) throw new WorkerError("แหล่งที่มาของคำขอไม่ถูกต้อง", 403);
  const worker = request.headers.get("x-dataview-worker") || "";
  const authorization = request.headers.get("authorization") || "";
  let url: URL;
  try { url = new URL(worker); } catch { throw new WorkerError("กรุณาเชื่อมต่อเครื่องดึงข้อมูลก่อนเริ่มวิเคราะห์", 401); }
  if (url.protocol !== "https:" || !/^[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com$/.test(url.hostname) || url.port || url.username || url.password || url.search || url.hash || url.pathname !== "/") throw new WorkerError("ลิงก์เครื่องดึงข้อมูลไม่ถูกต้อง กรุณาเปิดเว็บจากตัวเปิด DataView บนเครื่อง", 400);
  if (!/^Bearer [a-zA-Z0-9_-]{32,128}$/.test(authorization)) throw new WorkerError("กรุณาใส่รหัสเชื่อมต่อเครื่องดึงข้อมูลให้ถูกต้อง", 401);
  return { url: url.origin, authorization };
}
export async function workerRequest(request: Request, path: string, method = "GET", data?: unknown) {
  const { url, authorization } = connection(request);
  let response: Response;
  try {
    response = await fetch(`${url}${path}`, { method, headers: { Authorization: authorization, "Content-Type": "application/json" }, ...(data !== undefined ? { body: JSON.stringify(data) } : {}), signal: AbortSignal.timeout(12_000), cache: "no-store", redirect: "error" });
  } catch { throw new WorkerError("ติดต่อเครื่องดึงข้อมูลไม่ได้ กรุณาตรวจว่าเครื่องเปิดอยู่และตัวเปิด DataView ยังทำงานอยู่"); }
  let payload;
  try { payload = await response.json(); }
  catch { throw new WorkerError("เครื่องดึงข้อมูลออฟไลน์หรือลิงก์การเชื่อมต่อหมดอายุ กรุณาเปิด DataView บนเครื่องอีกครั้ง"); }
  if (!response.ok) throw new WorkerError(typeof payload.error === "string" ? payload.error : "เครื่องดึงข้อมูลตอบกลับไม่สำเร็จ", [400, 401, 404, 409, 429].includes(response.status) ? response.status : 502);
  return payload;
}
export function errorResponse(error: unknown) {
  return Response.json({ error: error instanceof Error ? error.message : "ส่งคำขอไม่สำเร็จ" }, { status: error instanceof WorkerError ? error.status : 400, headers: { "Cache-Control": "no-store" } });
}
