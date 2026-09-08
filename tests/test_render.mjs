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
             buildStamp, playedBy, threatRows, cardPosition, esc, inspectCard,
             winningChart, activeCut, bestConverterTile, winRateLabel,
             winRateNote, convertingArchetypes };
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
  app.state.resultCut = null;
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

/** Two non-brew archetypes from a report copy, for tests that reshape their numbers. */
function allTwo(meta) {
  const found = [];
  for (const pair of meta.pairs) {
    for (const variant of pair.variants) {
      if (!variant.is_brew) found.push(variant);
      if (found.length === 2) return found;
    }
  }
  return found;
}

/**
 * The notes disclosure belonging to one chart, by its toggle id.
 *
 * Per chart, not per page: an assertion that a phrase appears *somewhere* passed when
 * the ink chart lost its movement note, because the pair chart still carried the same
 * sentence. Each chart has to explain itself.
 */
function chartNotes(html, id) {
  const marker = `data-table-toggle="${id}"`;
  const at = html.indexOf(marker);
  if (at === -1) return null;
  const end = html.indexOf("</section>", at);
  const block = /<details class="notes">([\s\S]*?)<\/details>/.exec(html.slice(at, end));
  return block ? prose(block[1].replace(/<[^>]+>/g, " ")).trim() : "";
}

/** The page's own escaper, so a label with an apostrophe is compared as rendered. */
const esc0 = (value) => app.esc(value);

/**
 * Rendered HTML with its whitespace collapsed, for asserting on a sentence.
 *
 * Prose in this page lives in template literals and keeps their line breaks and
 * indentation, so a regex for a phrase that happens to wrap matches nothing. That is
 * a test failing for a reason unrelated to the page, which is the worst kind.
 */
const prose = (html) => html.replace(/\s+/g, " ");

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

  // Each of the three charts explains movement itself; a page-wide check passed once
  // when one of them lost its note and a sibling still carried the same sentence.
  const overview = render(meta, "");
  for (const id of ["archetypes", "pairs", "inks"]) {
    const notes = chartNotes(overview, id);
    check(
      notes !== null && /cut in two/.test(notes),
      `the ${id} chart carries the movement note: ${String(notes).slice(0, 70)}`
    );
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
  check(/rebuild it/i.test(prose(html)), "and what to do about it");
  check(!/class="delta/.test(html), "and draws no movement deltas");
  // The results axis is a different measurement and must not go down with movement.
  check(
    /class="interval/.test(html),
    "while the results axis, which is not movement, keeps its intervals"
  );

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
  check(prose(html).includes("only 3 deck(s)"), "the reason is on the page, in words");
  check(!/class="delta/.test(html), "and no row pretends to have moved");
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
    /names archetypes, not ink pairs/.test(prose(html)),
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

/**
 * The overview answers both questions: what you will face, and what is winning.
 *
 * Every chart in this report used to rank by how many people played a deck. On a real
 * field the most played archetype took 19% of the field and 11% of the top finishes -
 * the deck to expect and not the deck to beat - and nothing on the page said so.
 */
function test_the_overview_ranks_on_results_as_well_as_popularity() {
  const meta = report();
  const html = render(meta, "");

  check(html.includes("What is winning"), "the results chart is on the overview");
  check(html.includes("The field right now"), "and the field chart still is");
  check(/Result cut/.test(html), "the cut is selectable");
  check(/Best converter/.test(html), "and the KPI row carries the results axis");

  // Every cut the report computed must be offered, and the report's own default
  // must be the one selected when the reader has not chosen.
  for (const cut of meta.results.cuts) {
    check(
      html.includes(`value="${cut.key}"`),
      `the ${cut.label} cut is offered`
    );
  }
  app.state.meta = meta;
  app.state.resultCut = null;
  check(
    app.activeCut().key === meta.results.default,
    `an unchosen cut falls back to the report's default: ${app.activeCut().key}`
  );
}

/**
 * A cut too thin to read is withheld with its arithmetic, not shown as noise.
 *
 * With three decks in a cut every archetype in it is a third of "the winners", and a
 * chart of that reads as a finding.
 */
function test_a_thin_cut_is_withheld_and_says_why() {
  const meta = report((r) => {
    r.results.cuts = r.results.cuts.map((cut) => ({ ...cut, decks: 3, usable: false }));
  });
  app.state.meta = meta;
  app.state.resultCut = meta.results.cuts[0].key;
  const html = app.winningChart();
  app.state.resultCut = null;

  check(/Not shown for this cut/.test(html), "the chart is withheld");
  check(/3 deck/.test(prose(html)), "and names how few decks made it");
  check(!html.includes("bar-row"), "with no bars drawn");
  check(/Result cut/.test(html), "but the picker stays, so a wider cut is reachable");
}

/** A cut that separates nothing at some events has to admit it. */
function test_a_cut_that_excludes_nothing_admits_it() {
  const meta = report((r) => {
    r.results.cuts = r.results.cuts.map((cut) => ({
      ...cut,
      usable: true,
      decks: 20,
      vacuous_events: 3,
      events: 4,
    }));
  });
  app.state.meta = meta;
  app.state.resultCut = meta.results.cuts[0].key;
  const html = app.winningChart();
  app.state.resultCut = null;

  check(
    /excludes nothing/.test(prose(html)),
    "the page says the cut did not separate those events"
  );
  check(/3 of 4 events/.test(prose(html)), "and how many of them there were");
}

/** Bucketed placings that no cut could judge are counted, not dropped in silence. */
function test_decks_no_cut_could_judge_are_counted() {
  const meta = report((r) => {
    r.results.cuts = r.results.cuts.map((cut) => ({
      ...cut,
      usable: true,
      decks: 20,
      unknown: 7,
    }));
  });
  app.state.meta = meta;
  app.state.resultCut = meta.results.cuts[0].key;
  const html = app.winningChart();
  app.state.resultCut = null;

  check(
    /7 deck\(s\) could not be judged/.test(prose(html)),
    "the unjudged decks are named"
  );
  check(
    /left out of these figures/.test(prose(html)),
    "and said to be left out, not failed"
  );
  check(/bracket/.test(html), "with the reason - the source publishes brackets");
}

/**
 * The selection the whole axis is conditional on has to be stated.
 *
 * The field is already cut to the top N finishes fetched, so "conversion" is which of
 * the decks already doing well went furthest - not a win rate against a whole
 * tournament, which is how it would otherwise be read.
 */
function test_the_results_axis_states_what_it_is_conditional_on() {
  const meta = report();
  app.state.meta = meta;
  const html = app.winningChart();
  check(
    /conditional on making the fetched cut/.test(prose(html)),
    "the selection bias is stated where the numbers are"
  );
  check(
    /not a win rate against a whole tournament/.test(prose(html)),
    "and what the numbers are not"
  );
}

/** An older report without the results block degrades instead of throwing. */
function test_a_report_without_results_still_renders() {
  const meta = report((r) => delete r.results);
  let html;
  try {
    html = render(meta, "");
  } catch (error) {
    failures.push(`a report with no results block throws: ${error.message}`);
    return;
  }
  check(/Not in this report/.test(html), "the chart says it cannot answer");
  check(/rebuild it/i.test(prose(html)), "and what to do");
  check(!html.includes("undefined"), "and renders no undefined");
}

/** Match win rate is the sturdiest performance number here, so it gets a column. */
function test_match_win_rate_is_a_column_not_only_a_tooltip() {
  const meta = report();
  const twin = tableTwin(meta, "archetypes");
  const label = app.winRateLabel();
  check(
    twin.columns.includes(label),
    `the archetype table shows it, got ${JSON.stringify(twin.columns)}`
  );
  check(
    /%|–/.test(twin.cell(label) || ""),
    `and the cell carries a value: ${JSON.stringify(twin.cell(label))}`
  );
}

/**
 * The win rate must name the sample it was measured on.
 *
 * Every deck in the report finished inside the fetched cut, so the figure is a win
 * rate among lists that already placed - uniformly high and compressed. Checked
 * against inkdecks' own matrix over the same window, ours ran 11 points high in every
 * ink pair, turning 34 points of real spread into 8. Labelled "Match win rate" it
 * read as how often a deck wins, which it is not.
 */
function test_the_win_rate_names_the_sample_it_came_from() {
  const meta = report();
  app.state.meta = meta;

  check(
    app.winRateLabel().includes("top-32"),
    `the label names the cut: ${app.winRateLabel()}`
  );
  check(
    !/match win rate/i.test(app.winRateLabel()),
    `and does not claim to be a plain match win rate: ${app.winRateLabel()}`
  );
  check(
    /already placed/.test(app.winRateNote()),
    "the caveat says what the sample is"
  );

  const html = render(meta, "");
  check(!/match win rate/i.test(html), "the overview never uses the old label");
  check(
    prose(html).includes(app.winRateLabel()),
    "and shows the honest one"
  );
  check(
    /win rates among decks that already placed/.test(prose(html)),
    "with the caveat beside the chart that ranks on results"
  );

  const pair = render(meta, `pair/${meta.pairs[0].key}`);
  check(!/match win rate/i.test(pair), "nor does a pair page");
  check(prose(pair).includes(app.winRateLabel()), "which carries the honest label too");

  const about = render(meta, "about");
  check(
    /11 points high/.test(prose(about)),
    "and About quantifies how far off the old reading was"
  );

  // With no placing cut there is no cut to name, and it must not print "top-null".
  const uncut = report((r) => {
    r.filters.top = null;
  });
  app.state.meta = uncut;
  check(
    app.winRateLabel() === "Win rate, placed lists",
    `an uncut field still names its sample: ${app.winRateLabel()}`
  );
  check(!/null|undefined/.test(app.winRateNote()), "and the note stays clean");
}

/**
 * The results chart ranks on the rate, not on how big an archetype is.
 *
 * It used to sort by share of the top finishes, which put the largest archetype first
 * because it was largest - under a heading saying "what is winning". On a real field
 * the leader that produced was a deck whose share of the top finishes was *below* its
 * share of the field.
 */
function test_the_results_chart_ranks_on_the_rate() {
  const meta = report((r) => {
    // A big archetype that converts badly, and a small one that converts well.
    const [big, small] = allTwo(r);
    Object.assign(big.results.top10pct, {
      decks: 3, judged: 60, conversion: 5.0, conversion_low: 1.7,
      conversion_high: 13.9, share_of_cut: 60.0, unknown: 0,
    });
    big.decks = 60;
    big.share_of_field = 60.0;
    Object.assign(small.results.top10pct, {
      decks: 8, judged: 10, conversion: 80.0, conversion_low: 49.0,
      conversion_high: 94.3, share_of_cut: 20.0, unknown: 0,
    });
    small.decks = 10;
    small.share_of_field = 10.0;
  });
  app.state.meta = meta;
  app.state.resultCut = "top10pct";
  const cut = app.activeCut();
  const ranked = app.convertingArchetypes(cut);
  app.state.resultCut = null;

  check(ranked.length >= 2, `at least two archetypes rank: ${ranked.length}`);
  const rates = ranked.map((a) => a.results.top10pct.conversion);
  const sorted = [...rates].sort((x, y) => y - x);
  check(
    JSON.stringify(rates) === JSON.stringify(sorted),
    `ordered by conversion, got ${JSON.stringify(rates)}`
  );
  check(
    ranked[0].results.top10pct.conversion === 80.0,
    `the converter leads, not the big archetype: ${ranked[0].label} at ${rates[0]}%`
  );
  // Against the big archetype specifically: other archetypes in the sample field sit
  // between the two, so comparing with whatever landed second proves nothing.
  const leader = ranked[0].results.top10pct;
  const biggest = ranked.find((a) => a.results.top10pct.share_of_cut === 60.0);
  check(biggest !== undefined, "the big archetype is still charted");
  check(
    biggest && leader.share_of_cut < biggest.results.top10pct.share_of_cut,
    "and the leader holds a smaller share of those finishes than the big one"
  );
  check(
    biggest && ranked.indexOf(biggest) > 0,
    `the big archetype is not first: position ${biggest && ranked.indexOf(biggest)}`
  );
}

/** A rate needs lists behind it before it is charted at all. */
function test_a_rate_from_too_few_lists_is_not_charted() {
  const floor = built.results.min_rate_decks;
  check(floor >= 8, `the report publishes a floor: ${floor}`);

  const meta = report((r) => {
    const [thin] = allTwo(r);
    Object.assign(thin.results.top10pct, {
      decks: 3, judged: 3, conversion: 100.0, conversion_low: 43.8,
      conversion_high: 100.0, share_of_cut: 2.5, unknown: 0,
    });
    thin.decks = 3;
    thin.label = "Three Lists And A Dream";
  });
  app.state.meta = meta;
  app.state.resultCut = "top10pct";
  const ranked = app.convertingArchetypes(app.activeCut());
  const html = app.winningChart();
  app.state.resultCut = null;

  check(
    !ranked.some((a) => a.label === "Three Lists And A Dream"),
    "a three-list archetype does not rank, whatever its rate"
  );
  check(
    !html.includes("Three Lists And A Dream"),
    "and does not appear on the chart"
  );
  // Left out and said so: the arithmetic, not just a count.
  check(
    /archetypes have the \d+ judged lists a rate needs/.test(prose(html)),
    `the chart states what it can speak for: ${prose(html).slice(0, 200)}`
  );
  check(
    /% of the field; the other \d+ are too small to rank/.test(prose(html)),
    "including the share of the field it covers"
  );
}

/** Every charted rate shows the interval that qualifies it. */
function test_every_charted_rate_shows_its_interval() {
  const meta = report();
  app.state.meta = meta;
  const html = app.winningChart();
  const bars = (html.match(/class="bar-row"/g) || []).length;
  const intervals = (html.match(/class="interval"/g) || []).length;
  check(bars > 0, `the chart drew bars: ${bars}`);
  check(
    intervals === bars,
    `every bar carries an interval: ${intervals} of ${bars}`
  );
  check(
    /a rate from ten lists and one from a hundred are not the same claim/.test(prose(html)),
    "and the chart says why the interval is there"
  );
  // How to read the order is a separate statement, tested with the separation note.
  check(
    /(not a ranking|clearly behind it)/.test(prose(html)),
    "and how much of its own order the data supports"
  );
}

/**
 * A report whose rates carry no denominator must not be ranked at all.
 *
 * Found by rendering a real report built before this change: with `judged` missing the
 * floor reads as zero, so a three-list archetype that converted all three became
 * "Best converter". Degrading is the only honest option.
 */
function test_a_report_without_denominators_is_not_ranked() {
  const meta = report((r) => {
    for (const pair of r.pairs) {
      for (const variant of pair.variants) {
        for (const key of Object.keys(variant.results)) {
          delete variant.results[key].judged;
          delete variant.results[key].conversion_low;
          delete variant.results[key].conversion_high;
        }
      }
    }
  });
  check(meta.results.rankable === false, "the report is marked unrankable");
  app.state.meta = meta;
  const html = app.winningChart();
  check(/Not in this report/.test(html), "the chart withholds itself");
  check(
    /cannot be ranked without that/.test(prose(html)),
    `and says why: ${prose(html).slice(0, 240)}`
  );
  check(!html.includes("bar-row"), "with no bars");
  const tile = app.bestConverterTile();
  check(
    !/\d/.test(tile.replace(/<[^>]*>/g, "").replace(/[^0-9]/g, "")) ||
      /not enough results/.test(tile),
    `and the tile claims nothing: ${tile.replace(/<[^>]+>/g, " ").trim()}`
  );
}

/**
 * A sorted bar chart reads as a ranking, so it has to say when there is not one.
 *
 * On a real 837-deck field every charted archetype's interval overlapped the
 * leader's - not one was measurably worse - and the chart still presented fourteen of
 * them in order. The order was an artefact of point estimates on a few dozen lists.
 */
function test_the_chart_says_when_its_order_is_not_a_ranking() {
  // Overlapping intervals throughout: no archetype is separable from the leader.
  const muddy = report((r) => {
    for (const pair of r.pairs) {
      for (const variant of pair.variants) {
        if (variant.is_brew) continue;
        Object.assign(variant.results.top10pct, {
          decks: 5, judged: 20, conversion: 25.0 + (variant.key.length % 5),
          conversion_low: 10.0, conversion_high: 50.0, unknown: 0,
        });
      }
    }
  });
  app.state.meta = muddy;
  app.state.resultCut = "top10pct";
  const html = app.winningChart();
  const tile = app.bestConverterTile();
  app.state.resultCut = null;

  check(
    /The order here is not a ranking/.test(prose(html)),
    `the chart disowns its own order: ${prose(html).slice(0, 180)}`
  );
  check(
    /none of them is measurably worse/.test(prose(html)),
    "and says what overlapping intervals mean"
  );
  check(
    /not measurably worse/.test(prose(tile)),
    `the tile does not crown a leader either: ${prose(tile.replace(/<[^>]+>/g, " "))}`
  );

  // Now one archetype clearly ahead of the rest: the chart may say so.
  const clear = report((r) => {
    const variants = [];
    for (const pair of r.pairs) {
      for (const variant of pair.variants) {
        if (!variant.is_brew) variants.push(variant);
      }
    }
    variants.forEach((variant, index) => {
      Object.assign(
        variant.results.top10pct,
        index === 0
          ? { decks: 80, judged: 100, conversion: 80.0, conversion_low: 71.0,
              conversion_high: 86.9, unknown: 0 }
          : { decks: 5, judged: 100, conversion: 5.0, conversion_low: 2.2,
              conversion_high: 11.2, unknown: 0 }
      );
    });
  });
  app.state.meta = clear;
  app.state.resultCut = "top10pct";
  const sharp = app.winningChart();
  app.state.resultCut = null;
  check(
    !/The order here is not a ranking/.test(prose(sharp)),
    "with a real gap it stops disowning the order"
  );
  check(
    /are clearly behind it/.test(prose(sharp)),
    `and counts what the data does separate: ${prose(sharp).slice(0, 200)}`
  );

  // A partial overlap is the case that separates a right comparison from a wrong one.
  // Identical or disjoint intervals answer the same either way, which let a mutation
  // comparing the wrong ends of the intervals pass.
  const partial = report((r) => {
    const variants = [];
    for (const pair of r.pairs) {
      for (const variant of pair.variants) {
        if (!variant.is_brew) variants.push(variant);
      }
    }
    variants.forEach((variant, index) => {
      // Leader 50% (40-60). One overlaps from below (30%, 20-45), the rest are clear
      // of it entirely (5%, 2-11).
      const shape =
        index === 0
          ? { conversion: 50.0, conversion_low: 40.0, conversion_high: 60.0 }
          : index === 1
            ? { conversion: 30.0, conversion_low: 20.0, conversion_high: 45.0 }
            : { conversion: 5.0, conversion_low: 2.0, conversion_high: 11.0 };
      Object.assign(variant.results.top10pct, { decks: 5, judged: 40, unknown: 0 }, shape);
    });
  });
  app.state.meta = partial;
  app.state.resultCut = "top10pct";
  const mixed = prose(app.winningChart());
  const charted = app.convertingArchetypes(app.activeCut()).length;
  app.state.resultCut = null;

  check(
    new RegExp(`${charted - 2} of the other ${charted - 1} archetypes are clearly behind`).test(
      mixed
    ),
    `the one overlapping from below is not counted as behind: ${mixed.slice(0, 240)}`
  );
  check(
    /The remaining 1 overlap it/.test(mixed),
    "and it is counted as overlapping instead"
  );
}

/**
 * No subtitle is a wall of text.
 *
 * The caveats had grown to 331 words above one bar chart and 637 across the overview,
 * a sentence at a time, each individually earned. When everything is caveated at the
 * same weight the ones that change how you read the chart are lost among the ones
 * that do not, so they now sit behind a disclosure - on the page, one click away.
 */
function test_no_subtitle_is_a_wall_of_text() {
  const html = render(report(), "");
  const subtitles = [...html.matchAll(/<p class="subtitle">([\s\S]*?)<\/p>/g)].map((m) =>
    prose(m[1].replace(/<[^>]+>/g, " ")).trim()
  );
  check(subtitles.length >= 4, `the overview has subtitles: ${subtitles.length}`);
  for (const subtitle of subtitles) {
    const words = subtitle.split(" ").filter(Boolean).length;
    check(
      words <= 120,
      `found a subtitle of ${words} words: ${subtitle.slice(0, 90)}…`
    );
  }
  check(
    (html.match(/<details class="notes">/g) || []).length >= 3,
    "each chart carries a notes disclosure"
  );
}

/**
 * Every caveat is still reachable, with the condition that produces it forced.
 *
 * The tempting way to shorten a wall of text is to delete it, and each of these
 * sentences is load-bearing - so each is checked for. Forced rather than looked for:
 * most of them only appear when something is true of the field, and a first version
 * of this test asserted them against whatever the last build happened to contain. It
 * passed on a real inkdecks report, where brews, vacuous cuts and unjudgeable
 * bracket labels all exist, and failed on the sample field, where none of them do -
 * which is the trap this file's own header warns about.
 */
function test_every_caveat_is_reachable_when_it_applies() {
  // Conditions the sample field does not produce: a brew, a cut that separates
  // nothing at some events, and decks no cut can place.
  const meta = report((r) => {
    const pair = r.pairs[0];
    const variant = pair.variants[pair.variants.length - 1];
    Object.assign(variant, { is_brew: true, decks: 1, cards: [], cost_curve: [] });
    r.results.cuts = r.results.cuts.map((cut) => ({
      ...cut,
      usable: true,
      decks: Math.max(cut.decks, 20),
      vacuous_events: 3,
      unknown: 7,
    }));
  });
  const readable = prose(render(meta, ""));

  const required = {
    "one-off lists": "what the archetype chart leaves out",
    "judged lists a rate needs": "what the rate floor excludes",
    "95% interval": "why the interval is there",
    "in it for free": "the cut's own bias, measured",
    "knockout brackets": "why some decks cannot be judged",
    "already placed": "the win rate's sample",
    "cut in two": "what movement is",
  };
  for (const [phrase, why] of Object.entries(required)) {
    check(readable.includes(phrase), `"${phrase}" (${why}) is still on the page`);
  }
}

/**
 * Paper cannot be clicked, so print must not hide anything behind a disclosure.
 */
function test_print_opens_every_disclosure() {
  const css = readFileSync(join(ROOT, "site", "assets", "style.css"), "utf8");
  const print = /@media print \{([\s\S]*)\}/.exec(css);
  check(print !== null, "there is a print block");
  if (!print) return;
  check(
    /details\.notes > summary \{\s*display: none/.test(print[1]),
    "the toggle itself is not printed"
  );
  check(
    /details\.notes > p \{\s*display: block !important/.test(print[1]),
    "and the notes inside are forced open"
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
  test_the_overview_ranks_on_results_as_well_as_popularity,
  test_a_thin_cut_is_withheld_and_says_why,
  test_a_cut_that_excludes_nothing_admits_it,
  test_decks_no_cut_could_judge_are_counted,
  test_the_results_axis_states_what_it_is_conditional_on,
  test_a_report_without_results_still_renders,
  test_match_win_rate_is_a_column_not_only_a_tooltip,
  test_the_win_rate_names_the_sample_it_came_from,
  test_the_results_chart_ranks_on_the_rate,
  test_a_rate_from_too_few_lists_is_not_charted,
  test_every_charted_rate_shows_its_interval,
  test_a_report_without_denominators_is_not_ranked,
  test_the_chart_says_when_its_order_is_not_a_ranking,
  test_no_subtitle_is_a_wall_of_text,
  test_every_caveat_is_reachable_when_it_applies,
  test_print_opens_every_disclosure,
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
