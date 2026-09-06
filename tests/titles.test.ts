import { test } from "node:test";
import assert from "node:assert/strict";
import { normalizeTitle } from "../app/lib/titles.ts";

test("all-caps headline is fully title-cased, not partly left shouting", () => {
  const raw =
    'LEADER JEFFRIES IN LAS VEGAS: "HOUSE DEMOCRATS STAND SHOULDER TO SHOULDER WITH ORGANIZED LABOR"';
  assert.equal(
    normalizeTitle(raw),
    'Leader Jeffries in Las Vegas: "House Democrats Stand Shoulder to Shoulder with Organized Labor"'
  );
});

test("real acronyms stay uppercase", () => {
  assert.equal(
    normalizeTitle("SENATOR URGES FBI AND DOJ TO ACT ON ICE OVERSIGHT"),
    "Senator Urges FBI and DOJ to Act on ICE Oversight"
  );
  assert.equal(
    normalizeTitle("U.S. SENATOR ANNOUNCES NASA GRANT"),
    "U.S. Senator Announces NASA Grant"
  );
});

test("short non-acronyms are title-cased", () => {
  assert.equal(normalizeTitle("LAS VEGAS WIN FOR BIG SKY"), "Las Vegas Win for Big Sky");
});

test("small words keep their capital after opening punctuation", () => {
  assert.equal(
    normalizeTitle('REP. SMITH: "IN THIS BILL, THE WORK IS DONE"'),
    'Rep. Smith: "In This Bill, the Work is Done"'
  );
});

test("possessives and hyphenated compounds read correctly", () => {
  assert.equal(
    normalizeTitle("CONGRESS'S PRO-LABOR AGENDA AND O'ROURKE'S ROLE"),
    "Congress's Pro-Labor Agenda and O'Rourke's Role"
  );
});

test("mixed-case titles are left alone apart from entity decoding", () => {
  assert.equal(
    normalizeTitle("Sen. Smith&#39;s statement on the FBI report"),
    "Sen. Smith's statement on the FBI report"
  );
});
