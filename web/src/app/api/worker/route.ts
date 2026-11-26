import { errorResponse, workerRequest } from "@/lib/worker-proxy";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export async function GET(request: Request) {
  try { return Response.json(await workerRequest(request, "/health"), { headers: { "Cache-Control": "no-store" } }); }
  catch (error) { return errorResponse(error); }
}
