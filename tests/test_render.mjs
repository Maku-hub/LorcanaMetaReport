/* Tests that every page actually renders, and says what it is meant to say.
 *
 * `site/assets/app.js` is 1300 lines and had no test at all. Every page bug found
 * while building it was found by hand: a brew rendering an empty "Curve and card
 * types" card, "A one-off lists" for two decks, an archetype chart whose bars stopped
 * at 74% of the field without saying so, and a report missing the movement block
 * throwing during render and leaving a blank page. A blank page is the worst failure
 * this project has, because it carries no clue at all.
 *
 * Run it like the Python suites - no npm, no packages, no network:
 *
 *     node tests/test_render.mjs
 *
 * It needs a built report; `lorcana-meta build` first. The report is loaded once and
 * mutated in memory to reach the states a sample field may not contain (a brew, a
 * report with no movement), so the test does not depend on what the last build
 * happened to produce.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const APP_JS = join(ROOT, "site", "assets", "app.js");
const REPORT = join(ROOT, "site", "data", "meta.json");

const failures = [];

function check(condition, message) {
  if (!condition) failures.push(message);
}

/* --------------------------------------------------------------- the page */

/**
 * Evaluate app.js and hand back its renderers.
 *
 * The file is a plain browser script, not a module, so there is nothing to import.
 * It is evaluated as-is - `boot()` guards itself on `document` being defined - and
 * the stubs below are only what the top level touches. Anything a renderer needs
 * from the DOM would show up as a thrown error, which is the point.
 */
function load() {
  const source = readFileSync(APP_JS, "utf8");
  const stubs = `
    const window = { matchMedia: () => ({ matches: false }), addEventListener: () => {} };
    const localStorage = { getItem: () => null, setItem: () => {} };
    const location = { hash: "#/" };
  `;
  const exports = `
    return { state, renderOverview, renderPair, renderThreats, renderAbout,
             withDefaults, brewCoverage, movementNote, deltaText, deltaPlain,
             buildStamp, playedBy, threatRows, cardPosition, esc, inspectCard };
  `;
  return new Function(stubs + source + exports)();
}

const app = load();
const built = JSON.parse(readFileSync(REPORT, "utf8"));

/** A fresh deep copy, so one test cannot leak state into the next. */
function report(mutate) {
  const copy = JSON.parse(JSON.stringify(built));
  if (mutate) mutate(copy);
  return app.withDefaults(copy);
}

function render(meta, route) {
  app.state.meta = meta;
  app.state.tables = new Set();
  app.state.cardFilter = "";
  app.state.typeFilter = "";
  if (route && route.startsWith("pair/")) return app.renderPair(route.slice(5));
  if (route === "threats") return app.renderThreats();
  if (route === "about") return app.renderAbout();
  return app.renderOverview();
}

/**
 * The table twin behind chart `id`: its column headers and its first data row.
 *
 * The row matters as much as the header. A first attempt at this test checked only
 * that a "Movement" header existed, and a mutation that emptied every cell under it
 * passed - a column of blanks is exactly the silent failure being guarded against.
 */
function tableTwin(meta, id) {
  app.state.meta = meta;
  app.state.tables = new Set([id]);
  const html = app.renderOverview();
  app.state.tables = new Set();

  const head = /<thead><tr>(.*?)<\/tr><\/thead>/s.exec(html);
  const columns = head
    ? [...head[1].matchAll(/>([^<>]*)<\/th>/g)].map((m) => m[1].trim())
    : [];
  const body = /<tbody>\s*<tr>(.*?)<\/tr>/s.exec(html);
  const cells = body
    ? [...body[1].matchAll(/<td[^>]*>(.*?)<\/td>/gs)].map((m) => m[1].trim())
    : [];
  return { columns, cells, cell: (label) => cells[columns.indexOf(label)] };
}

/** The page's own escaper, so a label with an apostrophe is compared as rendered. */
const esc0 = (value) => app.esc(value);

const anyVariant = (meta, predicate) => {
  for (const pair of meta.pairs) {
    for (const variant of pair.variants) {
      if (predicate(variant)) return `pair/${pair.key}/${variant.key}`;
    }
  }
  return null;
};

/* ------------------------------------------------------------------ tests */

/** Nothing may render "undefined": that is a field the build stopped emitting. */
function test_no_page_renders_a_missing_value() {
  const meta = report();
  const routes = ["", "threats", "about", `pair/${built.pairs[0].key}`];
  const archetype = anyVariant(meta, (v) => !v.is_brew);
  if (archetype) routes.push(archetype);

  for (const route of routes) {
    let html;
    try {
      html = render(meta, route);
    } catch (error) {
      failures.push(`${route || "overview"} threw ${error.message}`);
      continue;
    }
    check(html.length > 200, `${route || "overview"} rendered ${html.length} chars`);
    for (const bad of ["undefined", "NaN", "[object Object]"]) {
      const hit = new RegExp(`.{0,60}${bad.replace(/[[\]]/g, "\\$&")}.{0,60}`).exec(html);
      if (hit) failures.push(`${route || "overview"} rendered ${bad}: …${hit[0].trim()}…`);
    }
  }
}

/**
 * A brew keeps what identifies it and loses what one deck cannot support.
 *
 * Forced rather than searched for: whether the last build produced a brew depends on
 * the field and the clustering threshold, and a test that quietly skips is not a test.
 */
function test_a_brew_loses_its_card_table_and_says_why() {
  const meta = report((r) => {
    const variant = r.pairs[0].variants[0];
    variant.is_brew = true;
    variant.decks = 1;
    variant.cards = [];
    variant.cost_curve = [];
    variant.trend = null;
  });
  const route = anyVariant(meta, (v) => v.is_brew);
  check(route !== null, "the forced brew is reachable");
  if (!route) return;

  const html = render(meta, route);
  check(!html.includes("Curve and card types"), "no empty curve card on a brew page");
  check(!html.includes("Distinct cards played"), "no distinct-cards tile claiming 0");
  check(html.includes("A one-off list"), "the page says what a brew is");
  check(!html.includes("A one-off lists"), "and says it grammatically for one deck");
  check(html.includes("Best finishes"), "a brew keeps its finishes");
  check(!html.includes("Movement in window"), "and gets no movement tile it cannot fill");

  // Two decks is the other side of BREW_MAX_DECKS and reads differently.
  const two = report((r) => {
    const variant = r.pairs[0].variants[0];
    Object.assign(variant, { is_brew: true, decks: 2, cards: [], cost_curve: [], trend: null });
  });
  const plural = render(two, anyVariant(two, (v) => v.is_brew));
  check(plural.includes("2 one-off lists"), "two decks reads as a plural");
}

/** A real archetype must still get everything a brew gives up. */
function test_a_real_archetype_keeps_its_card_table() {
  const meta = report();
  const route = anyVariant(meta, (v) => !v.is_brew && v.cards.length);
  check(route !== null, "the report has at least one archetype with cards");
  if (!route) return;

  const html = render(meta, route);
  check(html.includes("Card inclusion"), "the card table is there");
  check(html.includes("Curve and card types"), "so is the curve");
  check(html.includes("Distinct cards played"), "and the distinct-cards tile");
}

/**
 * The archetype chart does not cover the whole field, and has to say so.
 *
 * Two of the three overview charts account for every deck; this one leaves out
 * one-off brews, a quarter of a real field. Stating only the count of brews hid the
 * scale, and the three charts appeared to disagree with no way to reconcile them.
 */
function test_the_archetype_chart_states_how_much_of_the_field_it_covers() {
  const meta = report((r) => {
    // A field that is half brews, so the gap is unmistakable.
    const pair = r.pairs[0];
    pair.variants.forEach((variant, index) => {
      if (index % 2 === 0) {
        Object.assign(variant, { is_brew: true, cards: [], cost_curve: [] });
      }
    });
  });
  app.state.meta = meta;
  const note = app.brewCoverage();
  check(/% of the field/.test(note), `the coverage is a percentage: ${note}`);
  check(/\d+ decks/.test(note), `and names the decks: ${note}`);
  check(/one-off lists/.test(note), `and what the rest is: ${note}`);
  check(
    render(meta, "").includes("of the field ("),
    "and the overview carries it"
  );

  // With nothing left out, it must not invent a gap.
  const whole = report((r) =>
    r.pairs.forEach((p) => p.variants.forEach((v) => (v.is_brew = false)))
  );
  app.state.meta = whole;
  check(
    /Every deck in the field/.test(app.brewCoverage()),
    `a complete field says so: ${app.brewCoverage()}`
  );
}

/** Movement belongs beside every share, on all three charts or none. */
function test_all_three_charts_carry_movement_together() {
  const meta = report();
  if (!meta.trend.usable) {
    failures.push("the built report has no usable movement - rebuild over a wider window");
    return;
  }

  for (const id of ["archetypes", "pairs", "inks"]) {
    const twin = tableTwin(meta, id);
    check(
      twin.columns.includes("Movement"),
      `the ${id} table has a Movement column, got ${JSON.stringify(twin.columns)}`
    );
    // A header with nothing under it is the failure this guards against.
    const cell = twin.cell("Movement");
    check(
      /(\d\.\d pp|–)/.test(cell || ""),
      `the ${id} table's Movement cell carries a value, got ${JSON.stringify(cell)}`
    );
  }

  const html = render(meta, "");
  const values = (html.match(/bar-row__value/g) || []).length;
  const deltas = (html.match(/bar-row__after/g) || []).length;
  check(values > 0, "the overview drew some bars");
  check(deltas === values, `every bar carries a delta: ${deltas} of ${values}`);
}

/**
 * A dash is "we cannot tell", not "it did not move". They must not look alike.
 */
function test_a_row_below_the_floor_shows_a_dash_not_a_zero() {
  check(app.deltaPlain(null) === "–", `no trend is a dash, got ${app.deltaPlain(null)}`);
  check(
    app.deltaPlain({ delta: 0.0, first_share: 5, second_share: 5 }) === "0.0 pp",
    "a measured zero is a number"
  );
  check(
    /too few decks/.test(app.deltaText(null)),
    "and the dash says why on hover"
  );
  const up = app.deltaText({ delta: 4.1, first_share: 26.1, second_share: 30.2 });
  check(up.includes("+4.1 pp"), "a rise carries its sign in the text");
  check(up.includes("delta--rise"), "and its direction as a class");
  check(/points up/.test(up), "and in words, for a reader who cannot see the arrow");
  const down = app.deltaText({ delta: -4.1, first_share: 30.2, second_share: 26.1 });
  check(/points down/.test(down), "a fall too");
}

/**
 * A report built before movement existed must degrade, not blank the page.
 *
 * This is the one that would have hurt: several places read `meta.trend.usable`
 * without asking, and an older `meta.json` on disk is a normal thing to open.
 */
function test_an_older_report_without_movement_still_renders() {
  const meta = report((r) => delete r.trend);
  let html;
  try {
    html = render(meta, "");
  } catch (error) {
    failures.push(`an older report throws: ${error.message}`);
    return;
  }
  check(html.includes("Movement is not shown"), "the page says movement is unavailable");
  check(/rebuild it/.test(html), "and what to do about it");
  check(!html.includes("bar-row__after"), "no empty delta slots");

  for (const id of ["archetypes", "pairs", "inks"]) {
    check(
      !tableTwin(meta, id).columns.includes("Movement"),
      `the ${id} table drops the Movement column rather than filling it with dashes`
    );
  }
  check(render(meta, "about").includes("not shown"), "and the About page agrees");
}

/** Movement withheld for a thin window must state the reason it was withheld. */
function test_a_withheld_split_explains_itself() {
  const meta = report((r) => {
    r.trend.usable = false;
    r.trend.reason = "one half of the window holds only 3 deck(s)";
    r.pairs.forEach((p) => {
      p.trend = null;
      p.variants.forEach((v) => (v.trend = null));
    });
    r.inks.forEach((i) => (i.trend = null));
  });
  const html = render(meta, "");
  check(html.includes("only 3 deck(s)"), "the reason is on the page, in words");
  check(!html.includes("bar-row__after"), "and no row pretends to have a delta");
}

/** An empty field is a state the page has to survive, not a crash. */
function test_an_empty_field_does_not_throw() {
  const meta = report((r) => {
    r.pairs = [];
    r.inks = r.inks.map((ink) => ({ ...ink, decks: 0, share: 0.0, trend: null }));
    r.threats = [];
    r.totals = { ...r.totals, decks: 0, pairs: 0, variants: 0 };
  });
  for (const route of ["", "threats", "about"]) {
    try {
      render(meta, route);
    } catch (error) {
      failures.push(`${route || "overview"} throws on an empty field: ${error.message}`);
    }
  }
}

/** An unknown route is a typed URL, not a bug report. */
function test_an_unknown_pair_says_so_instead_of_throwing() {
  const meta = report();
  let html;
  try {
    html = render(meta, "pair/not-a-real-pair");
  } catch (error) {
    failures.push(`an unknown pair throws: ${error.message}`);
    return;
  }
  check(/Back to the field/.test(html), "it offers a way back");
}

/**
 * The build stamp has to name a dirty tree, not gloss over it.
 *
 * A report built with uncommitted changes cannot be reproduced from the commit it
 * names. A stamp that hides that is worse than no stamp, because it looks
 * trustworthy - so this checks the awkward case, not just the tidy one.
 */
function test_the_build_stamp_admits_an_unreproducible_build() {
  const dirty = report((r) => {
    r.built_by = { version: "9.9.9", commit: "deadbee", dirty: true };
  });
  app.state.meta = dirty;
  const stamp = app.buildStamp();
  check(stamp.includes("9.9.9"), `the version is named: ${stamp}`);
  check(stamp.includes("deadbee"), `and the commit: ${stamp}`);
  check(/uncommitted/.test(stamp), `and the dirty tree: ${stamp}`);
  check(render(dirty, "about").includes("deadbee"), "the About page carries it");

  const clean = report((r) => {
    r.built_by = { version: "9.9.9", commit: "deadbee", dirty: false };
  });
  app.state.meta = clean;
  check(
    !/uncommitted/.test(app.buildStamp()),
    `a clean tree claims nothing: ${app.buildStamp()}`
  );

  // An install from a wheel has no repository, and that is not an error.
  const noGit = report((r) => {
    r.built_by = { version: null, commit: null, dirty: null };
  });
  app.state.meta = noGit;
  check(app.buildStamp() === "unknown", `no git reads as unknown: ${app.buildStamp()}`);
  check(!render(noGit, "about").includes("undefined"), "and renders no undefined");
}

/**
 * The threat board names archetypes and never averages them into their ink pair.
 *
 * This is the shape of the bug it replaced: "played by Amber/Amethyst 63.2%" where
 * one archetype ran the card in every list and another in none. The page must show
 * the decks, and the legend must say that is what it is showing.
 */
function test_the_threat_board_names_decks_not_ink_pairs() {
  const meta = report();
  const html = render(meta, "threats");

  check(html.includes("Played by"), "the column is there");
  check(
    /names archetypes, not ink pairs/.test(html),
    "and the page says which level it is naming"
  );

  const threat = meta.threats[0];
  check(
    Array.isArray(threat.archetypes),
    `threats carry archetype attribution, got ${Object.keys(threat).join(", ")}`
  );
  for (const group of threat.archetypes) {
    check(
      html.includes(esc0(group.label)) || threat.archetypes.indexOf(group) >= 3,
      `${group.label} appears in the table`
    );
  }
}

/** The "+N more" badge must count every contributor, not just the shipped ones. */
function test_the_overflow_badge_counts_contributors_the_payload_left_out() {
  const meta = report((r) => {
    const threat = r.threats[0];
    threat.archetypes = threat.archetypes.slice(0, 1);
    threat.contributor_count = 15; // capped payload, wide real field
  });
  app.state.meta = meta;
  const badge = /\+(\d+)</.exec(app.playedBy(meta.threats[0]));
  check(badge !== null, "an overflow badge is drawn");
  check(
    badge && Number(badge[1]) === 14,
    `it counts from contributor_count, not the shipped list: +${badge && badge[1]}`
  );
}

/** Cards carry movement too, and it can be sorted by. */
function test_the_threat_board_can_rank_by_what_the_field_is_picking_up() {
  const meta = report((r) => {
    r.threats.forEach((threat, index) => {
      threat.trend =
        index % 3 === 2
          ? null
          : { first_decks: 5, second_decks: 9, first_share: 10, second_share: 10 + index, delta: index };
    });
  });

  app.state.meta = meta;
  app.state.threatSort = "expected";
  const byExpected = render(meta, "threats");
  // The word also appears in the legend below the table, so assert the header cell:
  // a first version of this check passed with the column deleted.
  check(
    /<th[^>]*>Movement<\/th>/.test(byExpected),
    "the Movement column header is in the table"
  );
  check(/Rising fastest/.test(byExpected), "and the sort is offered");

  app.state.threatSort = "movement";
  app.state.meta = meta;
  const rows = app.threatRows();
  app.state.threatSort = "expected";

  const deltas = rows.filter((r) => r.trend).map((r) => r.trend.delta);
  const sorted = [...deltas].sort((a, b) => b - a);
  check(
    JSON.stringify(deltas) === JSON.stringify(sorted),
    "sorted by movement, biggest riser first"
  );
  // Cards with no delta must not lead a movement ranking, tied on nothing.
  const firstWithout = rows.findIndex((r) => !r.trend);
  const lastWith = rows.reduce((last, r, i) => (r.trend ? i : last), -1);
  check(
    firstWithout === -1 || firstWithout > lastWith,
    "cards with no delta sit below every card that moved"
  );
}

/**
 * The inspector answers "who plays this, and is it growing", not just what it does.
 *
 * It used to show only the printing - cost, type, rules text - which is everything you
 * could read off the physical card and none of what the report knows.
 */
function test_the_card_inspector_shows_where_the_card_sits_in_the_meta() {
  const meta = report();
  const threat = meta.threats[0];
  app.state.meta = meta;

  // Through showCard, not cardPosition: a first version tested the lookup directly
  // and passed with the inspector never rendering what the lookup returned.
  const body = app.inspectCard(threat.name);
  check(body !== null, "the inspector rendered something");
  check(/Chance you meet it/.test(body || ""), `field presence is shown: ${body}`);
  check(/Played by/.test(body || ""), "and the decks that play it");
  check(
    (body || "").includes(app.esc(threat.archetypes[0].label)),
    `naming the archetype: ${threat.archetypes[0].label}`
  );

  const position = app.cardPosition(threat.name);
  check(position !== null, `${threat.name} is found on the threat board`);
  check(
    position && position.archetypes.length > 0,
    "and carries the decks that play it"
  );

  // A card outside the board must say so rather than imply nobody plays it.
  check(app.cardPosition("Not A Real Card") === null, "an unlisted card returns null");

  // The lookup must not outlive the report it was built from.
  const other = report((r) => {
    r.threats = r.threats.slice(0, 1);
  });
  app.state.meta = other;
  const stale = app.cardPosition(threat.name);
  check(
    other.threats.some((t) => t.name === threat.name) === (stale !== null),
    "the lookup follows the current report, not the previous one"
  );
}

/* ------------------------------------------------------------------- main */

const tests = Object.entries({
  test_no_page_renders_a_missing_value,
  test_a_brew_loses_its_card_table_and_says_why,
  test_a_real_archetype_keeps_its_card_table,
  test_the_archetype_chart_states_how_much_of_the_field_it_covers,
  test_all_three_charts_carry_movement_together,
  test_a_row_below_the_floor_shows_a_dash_not_a_zero,
  test_an_older_report_without_movement_still_renders,
  test_a_withheld_split_explains_itself,
  test_an_empty_field_does_not_throw,
  test_an_unknown_pair_says_so_instead_of_throwing,
  test_the_build_stamp_admits_an_unreproducible_build,
  test_the_threat_board_names_decks_not_ink_pairs,
  test_the_overflow_badge_counts_contributors_the_payload_left_out,
  test_the_threat_board_can_rank_by_what_the_field_is_picking_up,
  test_the_card_inspector_shows_where_the_card_sits_in_the_meta,
});

for (const [name, run] of tests) {
  try {
    run();
  } catch (error) {
    failures.push(`${name} raised ${error.message}`);
  }
}

if (failures.length) {
  console.log(`${failures.length} failure(s):`);
  for (const failure of failures) console.log(`  - ${failure}`);
  process.exit(1);
}
console.log(`${tests.length} tests passed`);
