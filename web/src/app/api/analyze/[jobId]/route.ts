import { errorResponse, jobIdPattern, workerRequest } from "@/lib/worker-proxy";
export const runtime = "nodejs";
export const maxDuration = 30;
export const dynamic = "force-dynamic";
type Context = { params: Promise<{ jobId: string }> };
async function handle(request: Request, context: Context, method: "GET" | "DELETE") {
  try {
    const { jobId } = await context.params;
    if (!jobIdPattern.test(jobId)) throw new Error("รหัสงานไม่ถูกต้อง");
    return Response.json(await workerRequest(request, `/jobs/${jobId}`, method), { headers: { "Cache-Control": "no-store" } });
  } catch (error) { return errorResponse(error); }
}
export function GET(request: Request, context: Context) { return handle(request, context, "GET"); }
export function DELETE(request: Request, context: Context) { return handle(request, context, "DELETE"); }
