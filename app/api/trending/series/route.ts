import { NextRequest, NextResponse } from "next/server";
import { getTermSeries, sanitizeTrendingTerms } from "../../../lib/trending";

export async function GET(request: NextRequest) {
  const raw = request.nextUrl.searchParams.get("q") ?? "";
  const terms = sanitizeTrendingTerms(raw);

  if (terms.length === 0) {
    return NextResponse.json({ terms: [], series: {} });
  }

  const series = await getTermSeries(terms);

  return NextResponse.json(
    { terms, series },
    { headers: { "Cache-Control": "public, max-age=600, s-maxage=600" } }
  );
}
