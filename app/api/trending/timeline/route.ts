import { NextRequest, NextResponse } from "next/server";
import { getTermTimeline } from "../../../lib/trending";

export async function GET(request: NextRequest) {
  const term = request.nextUrl.searchParams.get("term") ?? "";
  const data = await getTermTimeline(term);
  return NextResponse.json(data, {
    headers: { "Cache-Control": "public, max-age=600, s-maxage=600" },
  });
}
