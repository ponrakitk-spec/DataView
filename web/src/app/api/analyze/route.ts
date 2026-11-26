import { parseInput } from "@/lib/analysis";
import { connection, errorResponse, jobIdPattern, workerRequest } from "@/lib/worker-proxy";
export const runtime = "nodejs";
export const maxDuration = 30;
export const dynamic = "force-dynamic";
export async function POST(request: Request) {
  try {
    connection(request);
    const text = await request.text();
    if (text.length > 4096) throw new Error("ข้อมูลคำขอมีขนาดใหญ่เกินไป");
    const raw = JSON.parse(text);
    const input = parseInput(raw);
    if (typeof raw.jobId !== "string" || !jobIdPattern.test(raw.jobId)) throw new Error("รหัสงานไม่ถูกต้อง");
    const payload = await workerRequest(request, "/jobs", "POST", { ...input, jobId: raw.jobId });
    return Response.json(payload, { status: 202, headers: { "Cache-Control": "no-store" } });
  } catch (error) { return errorResponse(error); }
}
