import { test } from "node:test";
import assert from "node:assert/strict";
import { buildCoverageRows } from "../app/lib/coverage.ts";

function houseRows(total: number, reaching: number) {
  return Array.from({ length: total }, (_, i) => ({
    id: `member-${i}`,
    reaches: i < reaching,
  }));
}

test("clean senators is a count of senators, never a release count", () => {
  const rows = buildCoverageRows({
    senateClean: 92,
    senateTotal: 100,
    senateDocumented: 3,
    houseRows: houseRows(435, 421),
    houseDocumentedIds: new Set<string>(),
    houseSeedRows: 437,
  });
  assert.equal(rows[0][1], "92 / 100");
});

test("a senate figure larger than the chamber is clamped", () => {
  const rows = buildCoverageRows({
    senateClean: 344,
    senateTotal: 100,
    senateDocumented: 3,
    houseRows: houseRows(435, 421),
    houseDocumentedIds: new Set<string>(),
    houseSeedRows: 437,
  });
  assert.equal(rows[0][1], "100 / 100");
});

test("documented members already clean are not counted twice", () => {
  // 421 of 435 reach January 2025; 17 documented gaps, 3 of which overlap
  // with the clean set. The old code published 438 / 435 and a -3 trouble list.
  const documented = new Set(
    // three overlap (indexes below 421), fourteen do not
    [...Array(3).keys()]
      .map((i) => `member-${i}`)
      .concat([...Array(14).keys()].map((i) => `member-${421 + i}`))
  );
  const rows = buildCoverageRows({
    senateClean: 92,
    senateTotal: 100,
    senateDocumented: 3,
    houseRows: houseRows(435, 421),
    houseDocumentedIds: documented,
    houseSeedRows: 437,
  });
  assert.equal(rows[3][1], "435 / 435");
  assert.equal(rows[4][1], "0");
});

test("the trouble list is never negative", () => {
  const documented = new Set(
    Array.from({ length: 435 }, (_, i) => `member-${i}`)
  );
  const rows = buildCoverageRows({
    senateClean: 92,
    senateTotal: 100,
    senateDocumented: 3,
    houseRows: houseRows(435, 430),
    houseDocumentedIds: documented,
    houseSeedRows: 437,
  });
  assert.equal(rows[4][1], "0");
  assert.match(rows[3][1], /^435 \/ 435$/);
});

test("percentages stay at or below 100", () => {
  const rows = buildCoverageRows({
    senateClean: 92,
    senateTotal: 100,
    senateDocumented: 3,
    houseRows: houseRows(435, 400),
    houseDocumentedIds: new Set(["member-401", "member-402"]),
    houseSeedRows: 437,
  });
  assert.equal(rows[2][1], "400 / 435");
  assert.equal(rows[3][1], "402 / 435");
  assert.equal(rows[4][1], "33");
});
