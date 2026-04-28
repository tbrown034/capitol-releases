import { ImageResponse } from "next/og";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { getReleaseById, CONTENT_TYPE_LABEL } from "../../lib/queries";
import { getSenatorPhotoUrl, getInitials } from "../../lib/photos";
import { normalizeTitle } from "../../lib/titles";
import { formatReleaseDate } from "../../lib/dates";

export const alt = "Capitol Releases — press release";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const PARTY_COLOR = {
  D: "#2563eb",
  R: "#dc2626",
  I: "#d97706",
} as const;

const PARTY_LABEL = {
  D: "Democrat",
  R: "Republican",
  I: "Independent",
} as const;

async function loadPhoto(rel: { senator_name: string; senator_id: string }) {
  const url = getSenatorPhotoUrl(rel.senator_name, rel.senator_id);
  if (!url) return null;
  try {
    const path = join(process.cwd(), "public", url);
    const data = await readFile(path);
    const base64 = data.toString("base64");
    return `data:image/jpeg;base64,${base64}`;
  } catch {
    return null;
  }
}

export default async function ReleaseOgImage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const rel = await getReleaseById(id);

  if (!rel) {
    return new ImageResponse(
      (
        <div
          style={{
            display: "flex",
            width: "100%",
            height: "100%",
            background: "#ffffff",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 64,
            color: "#171717",
            fontFamily: "serif",
          }}
        >
          Capitol Releases
        </div>
      ),
      { ...size }
    );
  }

  const title = normalizeTitle(rel.title);
  const truncatedTitle =
    title.length > 200 ? title.slice(0, 197).trimEnd() + "…" : title;
  const photo = await loadPhoto(rel);
  const partyColor = PARTY_COLOR[rel.party];
  const partyLabel = PARTY_LABEL[rel.party];
  const dateStr = formatReleaseDate(rel.published_at);
  const baseTypeLabel = CONTENT_TYPE_LABEL[rel.content_type] ?? "Release";
  const isDeleted = rel.deleted_at !== null;
  const typeBadgeText = isDeleted
    ? `${baseTypeLabel} · Removed from senate.gov`
    : baseTypeLabel;
  const sourceHost = (() => {
    try {
      return new URL(rel.source_url).hostname.replace(/^www\./, "");
    } catch {
      return "senate.gov";
    }
  })();
  const sourceLine = `Source: ${sourceHost}`;

  return new ImageResponse(
    (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          width: "100%",
          height: "100%",
          background: "#ffffff",
          padding: 60,
          fontFamily: "system-ui, sans-serif",
          color: "#171717",
        }}
      >
        {/* Top bar */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            borderBottom: "2px solid #171717",
            paddingBottom: 16,
            marginBottom: 32,
          }}
        >
          <div
            style={{
              display: "flex",
              fontSize: 22,
              fontWeight: 700,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
            }}
          >
            Capitol Releases
          </div>
          <div
            style={{
              display: "flex",
              fontSize: 18,
              color: "#525252",
              letterSpacing: "0.05em",
              textTransform: "uppercase",
            }}
          >
            {typeBadgeText}
          </div>
        </div>

        {/* Senator strip */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 20,
            marginBottom: 28,
          }}
        >
          {photo ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={photo}
              alt=""
              width={88}
              height={88}
              style={{
                width: 88,
                height: 88,
                borderRadius: 999,
                objectFit: "cover",
                border: `4px solid ${partyColor}`,
              }}
            />
          ) : (
            <div
              style={{
                display: "flex",
                width: 88,
                height: 88,
                borderRadius: 999,
                background: "#f5f5f5",
                border: `4px solid ${partyColor}`,
                alignItems: "center",
                justifyContent: "center",
                fontSize: 32,
                fontWeight: 700,
                color: "#525252",
              }}
            >
              {getInitials(rel.senator_name)}
            </div>
          )}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
            }}
          >
            <div style={{ display: "flex", fontSize: 30, fontWeight: 600 }}>
              {rel.senator_name}
            </div>
            <div
              style={{
                display: "flex",
                fontSize: 20,
                color: "#525252",
                marginTop: 4,
              }}
            >
              <span style={{ color: partyColor, fontWeight: 600 }}>
                {partyLabel}
              </span>
              <span style={{ margin: "0 10px", color: "#a3a3a3" }}>·</span>
              <span>{rel.state}</span>
              {dateStr && (
                <>
                  <span style={{ margin: "0 10px", color: "#a3a3a3" }}>·</span>
                  <span>{dateStr}</span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Headline */}
        <div
          style={{
            display: "flex",
            fontSize: title.length > 100 ? 44 : 56,
            lineHeight: 1.15,
            fontWeight: 700,
            fontFamily: "Georgia, 'Times New Roman', serif",
            flex: 1,
          }}
        >
          {truncatedTitle}
        </div>

        {/* Footer */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            borderTop: "1px solid #e5e5e5",
            paddingTop: 18,
            marginTop: 24,
            fontSize: 18,
            color: "#737373",
          }}
        >
          <div style={{ display: "flex" }}>capitolreleases.com</div>
          <div style={{ display: "flex" }}>{sourceLine}</div>
        </div>
      </div>
    ),
    { ...size }
  );
}
