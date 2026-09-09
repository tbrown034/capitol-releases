import { test } from "node:test";
import assert from "node:assert/strict";
import { createSourceCitations } from "../app/lib/source-citations.ts";

const release = {
  item_id: "wildfire-release",
  title: "Wildfire response",
  source_url: "https://example.senate.gov/wildfire",
  published_at: "2026-09-08",
};

test("two cited chunks of one release share one reader-facing reference", () => {
  const citations = createSourceCitations();
  const firstPassage = { ...release, id: "chunk-a", blocks: ["First fact."] };
  const secondPassage = { ...release, id: "chunk-b", blocks: ["Second fact."] };
  assert.deepEqual(
    [citations.numberFor(firstPassage), citations.numberFor(secondPassage)],
    [1, 1],
  );
  assert.equal(citations.sources.length, 1);
  assert.equal(citations.sources[0].source_url, release.source_url);
});

test("distinct releases remain separate even when their titles match", () => {
  const citations = createSourceCitations();
  assert.equal(citations.numberFor(release), 1);
  assert.equal(citations.numberFor({
    ...release, item_id: "another-release", source_url: "https://example.senate.gov/another",
  }), 2);
  assert.equal(citations.numberFor(release), 1);
  assert.deepEqual(citations.sources.map((source) => source.n), [1, 2]);
});
