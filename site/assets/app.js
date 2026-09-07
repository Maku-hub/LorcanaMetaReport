/* Lorcana Meta Report - static renderer.
 *
 * Reads data/meta.json (written by `python -m lorcana_meta build`) and renders it.
 * No dependencies, no build step: the file GitHub Pages serves is the file here.
 *
 * Charting rules this file sticks to, in case you extend it:
 *   - every chart compares magnitude, so every mark is the SAME hue (--bar) and
 *     length carries the value; category identity lives in the row label.
 *   - a value sits at each bar tip / column cap, the axis stays a hairline.
 *   - every chart has a table twin behind a toggle, so no value is colour- or
 *     hover-only.
 */

"use strict";

const DATA_URL = "data/meta.json";

const INK_CODES = {
  amber: "AMB",
  amethyst: "AME",
  emerald: "EME",
  ruby: "RUB",
  sapphire: "SAP",
  steel: "STL",
};

const state = {
  meta: null,
  route: { name: "overview", arg: "" },
  cardFilter: "",
  typeFilter: "",
  showFringe: false, // the long tail of one-off cards on a pair page
  threatSort: "expected", // or "movement": what the field is picking up fastest
  tables: new Set(), // ids of charts currently showing their table twin
};

/* ------------------------------------------------------------------ helpers */

const $ = (selector, root = document) => root.querySelector(selector);

function esc(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]
  );
}

function num(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  return Number(value).toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function pct(value, digits = 1) {
  return value === null || value === undefined ? "–" : `${num(value, digits)}%`;
}

/**
 * A share delta between the two halves of the window, in percentage points.
 *
 * "pp" not "%": a move from 20% to 25% is +5 percentage points, not +5%, and calling
 * it +5% invites reading it as a quarter more decks. Direction is carried by the
 * arrow and the sign, so the text still says which way it went when the colour is
 * gone - printed, or read by someone who cannot separate the two hues.
 *
 * `null` means the row did not have the decks to say anything, which is different
 * from having moved by zero, and reads differently on screen.
 */
function deltaText(trend) {
  if (!trend) return `<span class="delta delta--flat" title="too few decks to say">–</span>`;
  const value = trend.delta;
  const rounded = Math.abs(value) < 0.05;
  const arrow = rounded ? "→" : value > 0 ? "▲" : "▼";
  const cls = rounded ? "flat" : value > 0 ? "rise" : "fall";
  const sign = rounded ? "" : value > 0 ? "+" : "−";
  const label = rounded ? "unchanged" : `${num(Math.abs(value), 1)} points ${
    value > 0 ? "up" : "down"
  }`;
  return `<span class="delta delta--${cls}" title="${esc(
    `${pct(trend.first_share)} in the first half → ${pct(trend.second_share)} in the second`
  )}"><span aria-hidden="true">${arrow} ${sign}${num(
    Math.abs(value),
    1
  )} pp</span><span class="sr-only">${esc(label)}</span></span>`;
}

/** Plain-text twin of `deltaText`, for a table cell that has to stay copyable. */
function deltaPlain(trend) {
  if (!trend) return "–";
  if (Math.abs(trend.delta) < 0.05) return "0.0 pp";
  return `${trend.delta > 0 ? "+" : "−"}${num(Math.abs(trend.delta), 1)} pp`;
}

/** Fold a card name for the search box, so "elsa snow" finds "Elsa - Snow Queen". */
function normalizeName(name) {
  return String(name)
    .normalize("NFKD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function inkChip(ink) {
  const code = INK_CODES[ink] || "?";
  const label = ink.charAt(0).toUpperCase() + ink.slice(1);
  return `<span class="ink-chip ink-chip--${esc(ink)}" title="${esc(label)}">${code}</span>`;
}

function inkPairChips(inks) {
  return `<span class="ink-pair" aria-hidden="true">${(inks || []).map(inkChip).join("")}</span>`;
}

function cardButton(name) {
  return `<button type="button" data-card="${esc(name)}">${esc(name)}</button>`;
}

/* ------------------------------------------------------- chart components */

/**
 * Horizontal bar list. One hue, value at the tip, hairline baseline, and a table
 * twin behind a toggle.
 *
 * rows: [{label, inks?, value, valueText, after?, href?, tooltip?}]
 *
 * `valueText` is escaped; `after` is markup we built ourselves (a movement delta) and
 * is inserted as-is. Nothing user-supplied may reach it.
 */
function barChart(id, title, subtitle, rows, columns, options = {}) {
  const max = Math.max(...rows.map((r) => r.value), 0) || 1;
  const showTable = state.tables.has(id);
  // Archetype names ("Wreck-It Ralph + Madam Mim") need more room than ink pair
  // names, and a clipped label is worse than a narrower bar.
  const labelStyle = options.labelWidth ? ` style="--label-col:${options.labelWidth}"` : "";

  const bars = rows
    .map((row) => {
      const width = Math.max((100 * row.value) / max, 0.6);
      const tag = row.href ? "a" : "div";
      const href = row.href ? ` href="${esc(row.href)}"` : "";
      const tip = row.tooltip ? ` data-tip="${esc(JSON.stringify(row.tooltip))}"` : "";
      return `<${tag} class="bar-row"${href}${tip}>
          <div class="bar-row__label">
            ${row.inks ? inkPairChips(row.inks) : ""}
            <span>${esc(row.label)}</span>
          </div>
          <div class="bar-row__track"><div class="bar-row__fill" style="width:${width.toFixed(
            2
          )}%"></div></div>
          <div class="bar-row__value">${esc(row.valueText)}${
            row.after ? `<span class="bar-row__after">${row.after}</span>` : ""
          }</div>
        </${tag}>`;
    })
    .join("");

  const table = `<div class="table-wrap"><table>
      <thead><tr>${columns.map((c) => `<th class="${c.num ? "num" : ""}">${esc(c.label)}</th>`).join("")}</tr></thead>
      <tbody>${rows
        .map(
          (row) =>
            `<tr>${columns
              .map((c) => `<td class="${c.num ? "num" : ""}">${c.cell(row)}</td>`)
              .join("")}</tr>`
        )
        .join("")}</tbody>
    </table></div>`;

  return `<section class="card">
      <div class="card__head"><h2>${esc(title)}</h2></div>
      <p class="subtitle">${subtitle}</p>
      ${showTable ? table : `<div class="bars"${labelStyle}>${bars}</div>`}
      <div class="toggle-row">
        <button class="icon-button" data-table-toggle="${esc(id)}" type="button">
          ${showTable ? "Show chart" : "Show table"}
        </button>
      </div>
    </section>`;
}

/** Column chart for the ink-cost curve: ordered buckets, one hue, value on the cap. */
function costCurve(curve) {
  if (!curve || !curve.length) return "";
  const max = Math.max(...curve.map((c) => c.avg_cards), 0) || 1;
  const columns = curve
    .map(
      (bucket) => `<div class="column" data-tip="${esc(
        JSON.stringify({ title: `Cost ${bucket.cost}`, rows: [["Average cards", num(bucket.avg_cards, 2)]] })
      )}">
        <div class="column__cap">${num(bucket.avg_cards, 1)}</div>
        <div class="column__fill" style="height:${((100 * bucket.avg_cards) / max).toFixed(1)}%"></div>
      </div>`
    )
    .join("");
  const axis = curve.map((b) => `<span>${b.cost}</span>`).join("");
  return `<div class="columns">${columns}</div><div class="columns-axis">${axis}</div>`;
}

/**
 * The copy-count spread for one card, as a compact strip.
 *
 * A mean answers "how many on average", which is not the question a player has. The
 * strip answers "how many will I face" by showing the shape: one solid block means
 * the archetype agrees, two blocks at opposite ends mean it does not and the mean
 * between them is a number nobody plays.
 *
 * Segments use one hue at stepped opacity - more copies, more solid - so the strip
 * reads as an ordered scale rather than four unrelated categories, and never relies
 * on hue to tell 1 from 4. The counts are in the tooltip and the table view.
 */
function copiesSpread(spread, decks) {
  const entries = Object.entries(spread || {}).sort((a, b) => Number(a[0]) - Number(b[0]));
  if (!entries.length) return "";

  const total = entries.reduce((sum, [, n]) => sum + n, 0) || 1;
  const segments = entries
    .map(([copies, n]) => {
      const width = (100 * n) / total;
      // 1 copy -> faint, 4 copies -> solid. Stepped, not continuous, so adjacent
      // counts stay distinguishable.
      const strength = Math.min(Number(copies), 4);
      return `<span class="spread__seg" style="width:${width.toFixed(1)}%;opacity:${(
        0.3 +
        0.175 * strength
      ).toFixed(3)}" title="${n} of ${decks} deck(s) run ${copies}"></span>`;
    })
    .join("");

  const tip = {
    title: "Copies per deck",
    rows: entries.map(([copies, n]) => [
      `${copies} ${Number(copies) === 1 ? "copy" : "copies"}`,
      `${n} deck${n === 1 ? "" : "s"} (${Math.round((100 * n) / total)}%)`,
    ]),
  };
  return `<span class="spread" data-tip="${esc(JSON.stringify(tip))}">${segments}</span>`;
}

/** Inline meter for a table cell. */
function meter(value, max, text) {
  const width = Math.max((100 * value) / (max || 1), 0);
  return `<div class="meter">
      <div class="meter__track"><div class="meter__fill" style="width:${width.toFixed(1)}%"></div></div>
      <div class="meter__value">${esc(text)}</div>
    </div>`;
}

/**
 * Stat tile. `variant` picks the value's type size: numbers get the display size,
 * words get a smaller one - a long label like "Core Constructed" set at 52px just
 * wraps and overflows its card.
 *   ""           a number
 *   "hero"       the one display figure on the view
 *   "text"       a word or short phrase
 *   "hero-text"  the lead tile, but its value is words
 */
function tile(label, value, note, variant = "") {
  const classes = ["tile"];
  if (variant.startsWith("hero")) classes.push("tile--hero");
  if (variant.endsWith("text")) classes.push("tile--text");
  return `<div class="${classes.join(" ")}">
      <div class="tile__label">${esc(label)}</div>
      <div class="tile__value">${value}</div>
      ${note ? `<div class="tile__note">${note}</div>` : ""}
    </div>`;
}

/* ---------------------------------------------------------------- overview */

/**
 * Every archetype in the field, flattened out of its ink pair.
 *
 * Archetypes come from card overlap, not deck names - see cluster.py. That is why
 * this list is the headline rather than the ink-pair list: two decks sharing a pair
 * can be completely different, and one deck arrives under five different names.
 */
function allArchetypes(includeBrews = false) {
  const rows = [];
  for (const pair of state.meta.pairs) {
    for (const variant of pair.variants || []) {
      if (!includeBrews && variant.is_brew) continue;
      rows.push({ ...variant, pair });
    }
  }
  rows.sort((a, b) => b.decks - a.decks || a.label.localeCompare(b.label));
  return rows;
}

/**
 * How much of the field this chart's bars actually account for.
 *
 * The ink-pair and single-ink charts cover every deck. This one does not: one-off
 * brews are left out, and on a real field that is a quarter of it — 15 archetypes
 * covering 74%, with 67 brews holding the other 26%. Saying only "67 brews are left
 * out" gave the count but not the scale, so the three charts on this page appeared to
 * disagree about the same field with no way to reconcile them.
 *
 * So state the arithmetic. A reader adding the bars up and getting 74% should find
 * the missing 26% named here, not have to work out where it went.
 */
function brewCoverage() {
  const shown = allArchetypes();
  const all = allArchetypes(true);
  const brews = all.length - shown.length;
  if (!brews) return "Every deck in the field is in a chart below.";

  const total = state.meta.totals.decks || 1;
  const inBars = shown.reduce((sum, a) => sum + a.decks, 0);
  const inBrews = total - inBars;
  return `These ${num(shown.length)} archetypes are ${pct(
    (100 * inBars) / total
  )} of the field (${num(inBars)} of ${num(total)} decks). The rest — ${pct(
    (100 * inBrews) / total
  )}, ${num(inBrews)} decks — is ${num(brews)} one-off lists, seen once or twice each
    and too small to be an archetype, so they are not charted here. The ink pair and
    single ink charts below cover every deck.`;
}

/**
 * One sentence explaining the Movement column, for the charts that carry it.
 *
 * The delta lives beside the share it belongs to rather than in a table of its own.
 * A separate "what is moving" table meant two lists of the same decks with different
 * memberships side by side - one ranked by share, one by movement, one mixing in ink
 * pairs, one truncated - and the reader had to work out why they disagreed.
 *
 * The explanation still has to be here: "+4.1 pp" with nothing next to it invites the
 * reader to assume a previous report it was measured against.
 */
function movementNote() {
  const trend = state.meta.trend || {};
  if (!trend.usable) {
    return `<b>Movement is not shown</b> for this build: ${esc(
      trend.reason || "the window could not be split"
    )}.`;
  }
  return `<b>Movement</b> is this window cut in two at ${esc(trend.split)} - the back half
    against the front half, not a comparison with a previous report. A row needs
    ${num(trend.min_decks_per_row)} decks before it gets one; “–” means it has fewer.
    Shares are relative, so one deck rising pushes the others down without anybody
    playing them less.`;
}

function renderOverview() {
  const meta = state.meta;
  const { totals, period, pairs, inks, filters } = meta;
  const topPair = pairs[0];
  const archetypes = allArchetypes();
  const brews = allArchetypes(true).length - archetypes.length;

  const kpis = `<div class="kpis">
      ${tile(
        "Decklists analysed",
        num(totals.decks),
        `${esc(period.start)} → ${esc(period.end)} · ${num(totals.tournaments)} events`,
        "hero"
      )}
      ${tile(
        "Archetypes",
        num(archetypes.length),
        `across ${num(totals.pairs)} ink pairs${brews ? `, plus ${num(brews)} one-off brews` : ""}`
      )}
      ${tile(
        "Most played pair",
        topPair ? pct(topPair.share) : "–",
        topPair ? esc(topPair.label) : ""
      )}
      ${tile("Format", esc(filters.format || "–"), esc(meta.source.name), "text")}
    </div>`;

  const archetypeChart = barChart(
    "archetypes",
    "Archetypes by share of the field",
    `Decks grouped by what is in them rather than what players called them, so one deck
     under five names counts once and two different decks sharing an ink pair count
     separately. Named after the cards that distinguish them.
     ${brewCoverage()}
     ${movementNote()}`,
    archetypes.map((archetype) => ({
      label: archetype.label,
      inks: archetype.pair.inks,
      value: archetype.share_of_field,
      valueText: pct(archetype.share_of_field),
      after: meta.trend.usable ? deltaText(archetype.trend) : "",
      href: `#/pair/${archetype.pair.key}/${archetype.key}`,
      tooltip: {
        title: archetype.label,
        rows: [
          ["Ink pair", archetype.pair.label],
          ["Share of field", pct(archetype.share_of_field)],
          ["Decks", num(archetype.decks)],
          ["Match win rate", pct(archetype.record.win_rate)],
          [
            "Players called it",
            archetype.named_by_players.map((n) => n.name).join(", ") || "unnamed",
          ],
          ...(meta.trend.usable ? [["Movement", deltaPlain(archetype.trend)]] : []),
        ],
      },
    })),
    [
      { label: "Archetype", cell: (r) => `${inkPairChips(r.inks)} ${esc(r.label)}` },
      { label: "Share of field", num: true, cell: (r) => pct(r.value) },
      {
        label: "Decks",
        num: true,
        cell: (r) => num(archetypes.find((a) => a.label === r.label).decks),
      },
      ...(meta.trend.usable
        ? [
            {
              label: "Movement",
              num: true,
              cell: (r) => deltaPlain(archetypes.find((a) => a.label === r.label).trend),
            },
          ]
        : []),
      {
        label: "Also known as",
        cell: (r) =>
          esc(
            archetypes
              .find((a) => a.label === r.label)
              .named_by_players.map((n) => n.name)
              .join(", ") || "–"
          ),
      },
    ],
    { labelWidth: "300px" }
  );

  const pairRows = pairs.map((pair) => ({
    label: pair.label,
    inks: pair.inks,
    value: pair.share,
    valueText: pct(pair.share),
    after: meta.trend.usable ? deltaText(pair.trend) : "",
    href: `#/pair/${pair.key}`,
    tooltip: {
      title: pair.label,
      rows: [
        ["Share of field", pct(pair.share)],
        ["Decks", num(pair.decks)],
        ["Match win rate", pct(pair.record.win_rate)],
        ["Average placing", num(pair.record.avg_standing, 1)],
        ...(meta.trend.usable ? [["Movement", deltaPlain(pair.trend)]] : []),
      ],
    },
  }));

  const pairChart = barChart(
    "pairs",
    "Ink pair share of the field",
    `Every deck that placed inside the cut, grouped by its two inks. Click a row for its
     card list. ${movementNote()}`,
    pairRows,
    [
      { label: "Ink pair", cell: (r) => `${inkPairChips(r.inks)} ${esc(r.label)}` },
      { label: "Share", num: true, cell: (r) => pct(r.value) },
      {
        label: "Decks",
        num: true,
        cell: (r) => num(pairs.find((p) => p.label === r.label).decks),
      },
      ...(meta.trend.usable
        ? [
            {
              label: "Movement",
              num: true,
              cell: (r) => deltaPlain(pairs.find((p) => p.label === r.label).trend),
            },
          ]
        : []),
    ]
  );

  const inkRows = inks.map((ink) => ({
    label: ink.label,
    inks: [ink.ink],
    value: ink.share,
    valueText: pct(ink.share),
    after: meta.trend.usable ? deltaText(ink.trend) : "",
    tooltip: {
      title: ink.label,
      rows: [
        ["Decks playing it", num(ink.decks)],
        ["Share of decks", pct(ink.share)],
        ...(meta.trend.usable ? [["Movement", deltaPlain(ink.trend)]] : []),
      ],
    },
  }));

  const inkChart = barChart(
    "inks",
    "Single ink presence",
    `How many decks play each ink at all. A two-ink deck counts towards both, so these
     sum to about 200%. ${movementNote()}`,
    inkRows,
    [
      { label: "Ink", cell: (r) => `${inkPairChips(r.inks)} ${esc(r.label)}` },
      { label: "Share of decks", num: true, cell: (r) => pct(r.value) },
      {
        label: "Decks",
        num: true,
        cell: (r) => num(inks.find((i) => i.label === r.label).decks),
      },
      ...(meta.trend.usable
        ? [
            {
              label: "Movement",
              num: true,
              cell: (r) => deltaPlain(inks.find((i) => i.label === r.label).trend),
            },
          ]
        : []),
    ]
  );

  return `<h1>The field right now</h1>
    <p class="subtitle">
      ${num(totals.decks)} decklists from ${num(totals.tournaments)} ${esc(
        filters.format
      )} events between ${esc(period.start)} and ${esc(period.end)}${
        filters.top ? `, top ${filters.top} finishes only` : ""
      }.
    </p>
    ${kpis}
    ${caveats()}
    <div class="grid">${archetypeChart}</div>
    <div class="grid grid--2">${pairChart}${inkChart}</div>`;
}

/** Anything that would make the numbers misleading gets said out loud. */
function caveats() {
  const meta = state.meta;
  const notes = [];
  const anomalies = meta.anomalies || {};
  const totals = meta.totals || {};

  if (meta.source.name === "local") {
    notes.push(
      "These decks come from local files, not a tournament platform - treat them as a demo of the pipeline, not as the meta."
    );
  }
  if (totals.decks < 60) {
    notes.push(
      `Only ${num(totals.decks)} decks in this window. Percentages move a lot at this sample size - widen the window before drawing conclusions.`
    );
  }
  if (totals.thin_pairs_dropped) {
    notes.push(
      `${num(totals.thin_pairs_dropped)} ink pair(s) with fewer than ${
        meta.filters.min_pair_decks
      } decks (${num(totals.decks_dropped_thin_pairs)} decks) were left out as noise.`
    );
  }
  if (meta.source.skipped_decks) {
    notes.push(
      `${num(meta.source.skipped_decks)} deck(s) could not be fetched from ${esc(
        meta.source.name
      )} and are missing from the field.`
    );
  }
  if (anomalies.unknown_card_count) {
    notes.push(
      `${num(anomalies.unknown_card_count)} card name(s) in the source lists could not be matched to a printing and are missing from the card stats.`
    );
  }
  if (!notes.length) return "";
  return `<div class="warn">${notes.map(esc).join("<br />")}</div>`;
}

/* ------------------------------------------------------------ pair detail */

/** `#/pair/amber-amethyst` or `#/pair/amber-amethyst/v1` for one archetype in it. */
function renderPair(arg) {
  const [key, variantKey] = String(arg || "").split("/");
  const pair = state.meta.pairs.find((p) => p.key === key);
  if (!pair) {
    return `<h1>Unknown ink pair</h1><p class="subtitle">No decks recorded for “${esc(
      key
    )}” in this window. <a href="#/">Back to the field</a>.</p>`;
  }

  const variants = pair.variants || [];
  const variant = variantKey ? variants.find((v) => v.key === variantKey) : null;
  // Everything below reads from `scope`, so a variant page and the whole-pair page
  // are the same page with a narrower set of decks.
  const scope = variant || pair;
  const cards = state.meta.cards;
  const filter = normalizeName(state.cardFilter);
  // Fringe cards are the long tail - in a 14-deck pair, a card in one list is 7%
  // inclusion, and a hundred of them bury the cards that define the archetype.
  // Hidden by default, never dropped: the count says how many are behind the toggle.
  const fringe = scope.cards.filter((card) => card.tier === "fringe").length;
  const rows = scope.cards.filter((card) => {
    if (!state.showFringe && card.tier === "fringe") return false;
    if (state.typeFilter && (cards[card.name] || {}).base_type !== state.typeFilter) return false;
    return !filter || normalizeName(card.name).includes(filter);
  });

  const share = variant ? variant.share_of_field : pair.share;
  const record = scope.record;
  const kpis = `<div class="kpis">
      ${tile("Share of field", pct(share), `${num(scope.decks)} decks`, "hero")}
      ${tile("Match win rate", pct(record.win_rate), `${num(record.wins)}-${num(
        record.losses
      )}-${num(record.draws)}`)}
      ${tile("Average placing", num(record.avg_standing, 1), `${num(
        record.top8_decks
      )} top-8 finishes`)}
      ${tile(
        scope.cards.length ? "Distinct cards played" : "Lists in this group",
        scope.cards.length ? num(scope.cards.length) : num(scope.decks),
        scope.cards.length
          ? variant
            ? "across this archetype's lists"
            : "across every list in the pair"
          : "too few for inclusion rates"
      )}
      ${
        // Movement gets a tile only where there is a number; an empty tile beside four
        // full ones reads as a failure rather than as an absence.
        state.meta.trend.usable && scope.trend
          ? tile(
              "Movement in window",
              deltaPlain(scope.trend),
              `${pct(scope.trend.first_share)} → ${pct(scope.trend.second_share)}, split ${esc(
                state.meta.trend.split
              )}`
            )
          : ""
      }
    </div>`;

  // A brew carries no card table by design: for one or two decks, every card sits at
  // 100% inclusion and the spread is a single bin, which is a decklist dressed up as
  // an analysis. Say so rather than rendering an empty table.
  const cardTable = !scope.cards.length
    ? `<section class="card">
        <div class="card__head"><h2>Card inclusion</h2></div>
        <p class="subtitle">
          ${
            variant && variant.is_brew
              ? `${
                  scope.decks === 1
                    ? "A one-off list"
                    : `${num(scope.decks)} one-off lists`
                } - too few for an inclusion rate to mean anything: every card would read
                 100% and the copy spread would be a single bin. The tells above are what
                 distinguishes ${scope.decks === 1 ? "it" : "them"}; the finishes below are
                 where ${scope.decks === 1 ? "it" : "they"} came from.`
              : "No card data in this scope."
          }
        </p>
      </section>`
    : `<section class="card">
      <div class="card__head"><h2>Card inclusion</h2></div>
      <p class="subtitle">
        Of the ${num(scope.decks)} ${esc(variant ? variant.label : pair.label)} decks, how many
        run each card and how many copies. <b>Core</b> means at least 80% of lists play it - that
        is the archetype, not a pilot's preference.
        Showing ${num(rows.length)} of ${num(scope.cards.length)} cards.
      </p>
      <div class="filters">
        <input type="search" id="card-search" placeholder="Filter cards…" value="${esc(
          state.cardFilter
        )}" aria-label="Filter cards by name" />
        <label for="type-filter">Type</label>
        <select id="type-filter">
          <option value="">All</option>
          ${["Character", "Action", "Item", "Location"]
            .map(
              (type) =>
                `<option value="${type}"${state.typeFilter === type ? " selected" : ""}>${type}</option>`
            )
            .join("")}
        </select>
        <label><input type="checkbox" id="fringe-toggle"${
          state.showFringe ? " checked" : ""
        } /> include the ${num(fringe)} fringe cards (under 15% of lists)</label>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Card</th>
              <th class="num">Cost</th>
              <th>Played in</th>
              <th class="num">Copies</th>
              <th>Spread</th>
              <th class="num">Mean</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            ${
              rows.length
                ? rows
                    .map((card) => {
                      const info = cards[card.name] || {};
                      return `<tr>
                        <td class="name"><div class="card-name">${inkPairChips(
                          info.inks || []
                        )}${cardButton(card.name)}</div></td>
                        <td class="num">${num(info.cost)}</td>
                        <td>${meter(card.inclusion, 100, pct(card.inclusion, 0))}</td>
                        <td class="num"><b>${num(card.typical_copies)}×</b></td>
                        <td>${copiesSpread(card.copies_spread, card.decks)}</td>
                        <td class="num">${num(card.avg_copies, 2)}</td>
                        <td>${
                          card.tier === "core"
                            ? '<span class="badge badge--core">core</span>'
                            : card.tier === "fringe"
                            ? '<span class="badge">fringe</span>'
                            : '<span class="badge">flex</span>'
                        }</td>
                      </tr>`;
                    })
                    .join("")
                : `<tr><td colspan="7" class="empty">Nothing matches that filter.</td></tr>`
            }
          </tbody>
        </table>
      </div>
      <div class="legend">
        <span><b>Played in</b> share of these decks running at least one copy</span>
        <span><b>Copies</b> what most lists run - the mode, not the mean</span>
        <span><b>Spread</b> how many run 1 / 2 / 3 / 4; hover for the counts. One
          block means the lists agree, two at opposite ends mean they do not</span>
        <span><b>Mean</b> the average among the lists that run it, for reference</span>
      </div>
    </section>`;

  // A brew has no curve either - one deck's curve is not a curve, it is that deck.
  const shape = (scope.cost_curve || []).length
    ? `<section class="card">
        <div class="card__head"><h2>Curve and card types</h2></div>
        <p class="subtitle">Average cards at each ink cost, per deck.</p>
        ${costCurve(scope.cost_curve)}
        <div class="legend">
          ${(scope.type_mix || pair.type_mix)
            .map((t) => `<span><b>${esc(t.type)}</b> ${num(t.avg_cards, 1)} cards</span>`)
            .join("")}
        </div>
      </section>`
    : "";

  const finishes = `<section class="card">
      <div class="card__head"><h2>Best finishes</h2></div>
      <p class="subtitle">Where these lists came from.</p>
      <div class="table-wrap">
        <table>
          <thead><tr><th class="num">#</th><th>Player</th><th>Event</th><th>Date</th></tr></thead>
          <tbody>
            ${scope.examples
              .map(
                (row) => `<tr>
                  <td class="num">${esc(row.standing_label) || num(row.standing)}</td>
                  <td>${esc(row.player)}</td>
                  <td>${
                    row.url
                      ? `<a href="${esc(row.url)}" target="_blank" rel="noopener">${esc(
                          row.tournament
                        )}</a>`
                      : esc(row.tournament)
                  }${row.players ? ` <span class="badge">${num(row.players)} players</span>` : ""}</td>
                  <td>${esc(row.date)}</td>
                </tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>
    </section>`;

  const scopePicker =
    variants.length > 1
      ? `<div class="scope-picker">
          <a class="scope-pill${variant ? "" : " scope-pill--on"}" href="#/pair/${esc(
            pair.key
          )}">Whole pair · ${num(pair.decks)}</a>
          ${variants
            .map(
              (v) =>
                `<a class="scope-pill${
                  variant && variant.key === v.key ? " scope-pill--on" : ""
                }" href="#/pair/${esc(pair.key)}/${esc(v.key)}">${esc(v.label)} · ${num(
                  v.decks
                )}${v.is_brew ? " (brew)" : ""}</a>`
            )
            .join("")}
        </div>`
      : "";

  const archetypeCards =
    variants.length > 1 && !variant
      ? `<section class="card">
          <div class="card__head"><h2>Archetypes inside this pair</h2></div>
          <p class="subtitle">
            Split by card overlap, so the same deck stays together across pilots' tweaks and
            two genuinely different builds do not get averaged into one. The names players
            submitted are listed for reference only - they never decide the grouping.
          </p>
          ${variants
            .map((v) => {
              const aka = v.named_by_players
                .map((n) => `${esc(n.name)}${n.count > 1 ? ` ×${n.count}` : ""}`)
                .join(", ");
              return `<div class="archetype">
                  <div class="archetype__head">
                    <a href="#/pair/${esc(pair.key)}/${esc(v.key)}"><b>${esc(v.label)}</b></a>
                    ${v.is_brew ? '<span class="badge">one-off brew</span>' : ""}
                  </div>
                  ${meter(v.share_of_pair, 100, pct(v.share_of_pair, 0))}
                  <div class="archetype__meta">
                    ${num(v.decks)} decks · ${pct(v.share_of_field)} of the field ·
                    ${pct(v.record.win_rate)} match win rate
                  </div>
                  ${
                    v.signature.length
                      ? `<div class="archetype__sig">Tells: ${v.signature
                          .map(
                            (s) =>
                              `${cardButton(s.name)} <span class="badge">${pct(
                                s.inclusion,
                                0
                              )} here vs ${pct(s.elsewhere, 0)} elsewhere</span>`
                          )
                          .join(" ")}</div>`
                      : ""
                  }
                  ${aka ? `<div class="archetype__aka">Players called it: ${aka}</div>` : ""}
                </div>`;
            })
            .join("")}
        </section>`
      : "";

  const heading = variant
    ? `<h1>${inkPairChips(pair.inks)} ${esc(variant.label)}</h1>
       <p class="subtitle">
         ${esc(pair.label)} · ${pct(variant.share_of_field)} of the field ·
         <a href="#/pair/${esc(pair.key)}">whole pair</a> ·
         <a href="#/">back to the field</a>
         ${
           variant.named_by_players.length
             ? `<br />Players called this list: ${esc(
                 variant.named_by_players.map((n) => n.name).join(", ")
               )}`
             : ""
         }
       </p>`
    : `<h1>${inkPairChips(pair.inks)} ${esc(pair.label)}</h1>
       <p class="subtitle">
         ${pct(pair.share)} of the field · ${num(variants.length)} archetype(s) ·
         <a href="#/">back to the field</a>
       </p>`;

  return `${heading}
    ${scopePicker}
    ${kpis}
    ${archetypeCards}
    ${cardTable}
    <div class="grid grid--2">${shape}${finishes}</div>`;
}

/* --------------------------------------------------------------- threats */

function threatRows() {
  const filter = normalizeName(state.cardFilter);
  const rows = state.meta.threats.filter((threat) => {
    if (state.typeFilter && threat.base_type !== state.typeFilter) return false;
    return !filter || normalizeName(threat.name).includes(filter);
  });
  if (state.threatSort !== "movement") return rows;

  // Rising fastest, and only cards that have a delta at all - sorting by movement
  // would otherwise put every card the field is too thin to judge at the top, tied
  // on nothing. They stay in the list, below the cards that actually moved.
  const withDelta = rows.filter((threat) => threat.trend);
  const without = rows.filter((threat) => !threat.trend);
  withDelta.sort((a, b) => b.trend.delta - a.trend.delta);
  return [...withDelta, ...without];
}

function renderThreats() {
  const rows = threatRows();
  const maxExpected = Math.max(...state.meta.threats.map((t) => t.expected_copies), 0.01);
  const moving = state.meta.trend.usable;

  return `<h1>What you will actually face</h1>
    <p class="subtitle">
      Every card weighted by how popular the deck playing it is. <b>Expected copies</b> is how many
      copies sit in a deck drawn at random from this field - that is the number worth building tech
      against, because a four-of in a 5% deck matters less than a two-of in a 25% deck.
      <b>Played by</b> names archetypes, not ink pairs: one Amber/Amethyst deck can run a card in
      every list while another runs it in none, and the average of those two is a number nobody plays.
    </p>
    <div class="filters">
      <input type="search" id="card-search" placeholder="Filter cards…" value="${esc(
        state.cardFilter
      )}" aria-label="Filter cards by name" />
      <label for="type-filter">Type</label>
      <select id="type-filter">
        <option value="">All</option>
        ${["Character", "Action", "Item", "Location"]
          .map(
            (type) =>
              `<option value="${type}"${state.typeFilter === type ? " selected" : ""}>${type}</option>`
          )
          .join("")}
      </select>
      ${
        moving
          ? `<label for="threat-sort">Sort</label>
             <select id="threat-sort">
               <option value="expected"${
                 state.threatSort === "movement" ? "" : " selected"
               }>Expected copies</option>
               <option value="movement"${
                 state.threatSort === "movement" ? " selected" : ""
               }>Rising fastest</option>
             </select>`
          : ""
      }
    </div>
    <section class="card">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Card</th>
              <th class="num">Cost</th>
              <th>Expected copies</th>
              <th class="num">When you do</th>
              <th class="num">Chance you meet it</th>
              ${moving ? `<th class="num">Movement</th>` : ""}
              <th>Played by</th>
            </tr>
          </thead>
          <tbody>
            ${
              rows.length
                ? rows
                    .map(
                      (threat) => `<tr>
                        <td class="name"><div class="card-name">${inkPairChips(
                          threat.inks
                        )}${cardButton(threat.name)}</div></td>
                        <td class="num">${num(threat.cost)}</td>
                        <td>${meter(
                          threat.expected_copies,
                          maxExpected,
                          num(threat.expected_copies, 2)
                        )}</td>
                        <td class="num">${
                          threat.typical_copies ? `<b>${num(threat.typical_copies)}×</b>` : "–"
                        }</td>
                        <td class="num">${pct(threat.field_presence, 0)}</td>
                        ${moving ? `<td class="num">${deltaText(threat.trend)}</td>` : ""}
                        <td>${playedBy(threat)}</td>
                      </tr>`
                    )
                    .join("")
                : `<tr><td colspan="${
                    moving ? 7 : 6
                  }" class="empty">Nothing matches that filter.</td></tr>`
            }
          </tbody>
        </table>
      </div>
      <div class="legend">
        <span><b>Expected copies</b> averaged over the whole field, so it is fractional
          by design - the ranking to build tech against</span>
        <span><b>When you do</b> how many copies the deck actually runs, once you are
          sitting across from it</span>
        <span><b>Chance you meet it</b> odds a random deck in this field runs at least one copy</span>
        ${
          moving
            ? `<span><b>Movement</b> change in that chance between the halves of the window -
                 what the field is picking up, whether or not any deck moved</span>`
            : ""
        }
        <span><b>Played by</b> the archetypes running it, with their inclusion rate.
          One-off lists are pooled per ink pair: each is a single deck, so every card in
          it would read 100%</span>
      </div>
    </section>`;
}

/**
 * Which decks bring this card, most likely opponent first.
 *
 * Archetypes, not ink pairs. The pair-level version of this line was the last place
 * in the report still averaging a card across decks that share only their inks, and on
 * real data it produced "63.2%" where one archetype ran the card in every list and
 * another in none.
 */
function playedBy(threat) {
  const shown = threat.archetypes.slice(0, 3);
  // From the real count, not the shipped list: the payload caps contributors, so
  // subtracting from what arrived understates a staple spread across a dozen decks.
  const rest = threat.contributor_count - shown.length;
  const badges = shown
    .map((group) => {
      const label = `${esc(group.label)} ${pct(group.inclusion, 0)}`;
      // A pooled group of brews is not a place you can navigate to.
      return group.is_brews
        ? `<span class="badge" title="${esc(
            `${group.decks} one-off list(s) in ${group.pair_label}`
          )}">${label}</span>`
        : `<a class="badge" href="#/pair/${esc(group.pair)}" title="${esc(
            `${group.inclusion}% of its ${group.decks} decks run it, ${group.typical_copies}x ` +
              `typical - and this deck is ${group.share_of_field}% of the field`
          )}">${label}</a>`;
    })
    .join(" ");
  return badges + (rest > 0 ? ` <span class="badge">+${rest}</span>` : "");
}

function brewCount() {
  return (state.meta.pairs || []).reduce(
    (total, pair) => total + (pair.variants || []).filter((v) => v.is_brew).length,
    0
  );
}

/**
 * Which build produced this report.
 *
 * A dirty tree is called out rather than glossed over: a report built with
 * uncommitted changes cannot be reproduced from the commit it names, and a stamp that
 * hides that is worse than no stamp, because it looks trustworthy.
 */
function buildStamp() {
  // Read through `built_by` rather than aliasing it to a shorter local: the field is
  // what the report promises, and `tests/test_report_shape.py` matches the access
  // path. A local under a different name hides the read from that check - which is
  // why `anomalies`, `totals` and `filters` are all named after their field too.
  const built_by = state.meta.built_by || {};
  if (!built_by.version && !built_by.commit) return "unknown";
  const parts = [];
  if (built_by.version) parts.push(`v${esc(built_by.version)}`);
  if (built_by.commit) parts.push(esc(built_by.commit));
  if (built_by.dirty) parts.push("+ uncommitted changes");
  return parts.join(" · ");
}

function renderAbout() {
  const meta = state.meta;
  const anomalies = meta.anomalies || {};
  return `<h1>How these numbers are made</h1>
    <p class="subtitle">Every figure on this site comes from one JSON file, built by one command.</p>
    <div class="grid grid--2">
      <section class="card">
        <div class="card__head"><h2>Method</h2></div>
        <p class="subtitle">
          Tournament standings and the decklists attached to them are pulled for a date window, cut
          to the top ${esc(meta.filters.top || "all")} finishes of each event, and grouped by the two
          inks each list is built on. Card names are matched against a public card database; a list
          that cannot be read is dropped rather than guessed at.
        </p>
        <div class="table-wrap"><table><tbody>
          <tr><td>Window</td><td class="num">${esc(meta.period.start)} → ${esc(
            meta.period.end
          )} (${num(meta.period.days)} days)</td></tr>
          <tr><td>Format</td><td class="num">${esc(meta.filters.format)}</td></tr>
          <tr><td>Placing cut</td><td class="num">top ${esc(meta.filters.top || "all")}</td></tr>
          <tr><td>Event size floor</td><td class="num">${
            meta.filters.min_players ? `${num(meta.filters.min_players)} players` : "none"
          }</td></tr>
          <!-- The threshold decides what counts as the same deck, so every archetype
               number on the site moves with it. Showing it beats leaving the reader to
               guess which knob produced 15 archetypes rather than 18. -->
          <tr><td>Archetype similarity</td><td class="num">${num(
            100 * (meta.filters.cluster_threshold || 0)
          )}% card overlap</td></tr>
          <tr><td>Decklists fetched</td><td class="num">${num(
            meta.totals.decks_fetched
          )}</td></tr>
          <tr><td>Decklists read</td><td class="num">${num(
            meta.totals.decks_resolved
          )}</td></tr>
          <tr><td>Decklists used</td><td class="num">${num(meta.totals.decks)}</td></tr>
          <tr><td>Events</td><td class="num">${num(meta.totals.tournaments)}</td></tr>
          <tr><td>Cards detailed</td><td class="num">${num(
            meta.totals.cards_described
          )}</td></tr>
          <tr><td>Movement split</td><td class="num">${
            meta.trend.usable
              ? `${esc(meta.trend.first.start)} → ${esc(meta.trend.first.end)} (${num(
                  meta.trend.first.decks
                )}) vs ${esc(meta.trend.second.start)} → ${esc(meta.trend.second.end)} (${num(
                  meta.trend.second.decks
                )})`
              : "not shown"
          }</td></tr>
          <tr><td>Built</td><td class="num">${esc(meta.generated_at)}</td></tr>
          <tr><td>Built by</td><td class="num">${buildStamp()}</td></tr>
        </tbody></table></div>
      </section>
      <section class="card">
        <div class="card__head"><h2>What is missing</h2></div>
        <p class="subtitle">The gaps that matter when you read the percentages.</p>
        <ul class="subtitle">
          <li>Only events on the source platform are counted. It is a sample of the meta, not a census.</li>
          <li>A standing with no submitted decklist contributes nothing, which can bias a field toward players who share lists.</li>
          <li>Inclusion rates say what people played, not what won. Win rate per pair is a small-sample number - treat it as a hint.</li>
          <li>
            ${
              meta.trend.usable
                ? `Movement is this window cut at ${esc(
                    meta.trend.split
                  )} - not a comparison with a previous report, and not enough halves to
                   tell a trend from a busy weekend. A pair needs ${num(
                     meta.trend.min_decks_per_row
                   )} decks before it gets a delta at all.`
                : `No movement is shown: ${esc(meta.trend.reason || "the window could not be split")}.`
            }
          </li>
          <li>One-off lists (${num(
            brewCount()
          )} here, seen once or twice) keep their label, record and tells but carry no card
          table or curve: with one deck every card sits at 100% inclusion, which is a
          decklist wearing the clothes of an analysis.</li>
          ${
            meta.trend.usable && meta.trend.undated_decks
              ? `<li>${num(
                  meta.trend.undated_decks
                )} deck(s) carry no event date, so they count towards every share but sit in
                 neither half of the movement split.</li>`
              : ""
          }
          <li>${num(anomalies.unknown_card_count || 0)} unmatched card name(s), ${num(
            anomalies.short_decks || 0
          )} truncated list(s) and ${num(
            (anomalies.undetermined_inks || 0) + (anomalies.over_two_inks || 0)
          )} list(s) with unreadable inks were dropped from this build.</li>
        </ul>
      </section>
    </div>`;
}

/* ----------------------------------------------------------------- shell */

function renderFooter() {
  const source = state.meta.source;
  const credit = source.attribution_url
    ? `<a href="${esc(source.attribution_url)}" target="_blank" rel="noopener">${esc(
        source.attribution
      )}</a>`
    : esc(source.attribution);
  const cardDb = source.card_db
    ? `Card data from <a href="${esc(source.card_db.url)}" target="_blank" rel="noopener">${esc(
        source.card_db.name
      )}</a>.`
    : "";
  return `<footer class="credits">
      <div>${credit}. ${cardDb} Report built ${esc(state.meta.generated_at)}.</div>
      <div>
        Disney Lorcana is a trademark of Disney and Ravensburger. This is an unofficial fan project,
        not published, endorsed or approved by either.
      </div>
    </footer>`;
}

function parseRoute() {
  const hash = (location.hash || "#/").slice(2);
  const [name, ...rest] = hash.split("/");
  return { name: name || "overview", arg: rest.join("/") };
}

function render() {
  const view = $("#view");
  const route = state.route;

  let html;
  if (!state.meta) {
    html = `<div class="empty">Loading…</div>`;
  } else if (route.name === "pair") {
    html = renderPair(route.arg);
  } else if (route.name === "threats") {
    html = renderThreats();
  } else if (route.name === "about") {
    html = renderAbout();
  } else {
    html = renderOverview();
  }

  view.innerHTML = html + (state.meta ? renderFooter() : "");

  for (const tab of document.querySelectorAll("#tabs a")) {
    const target = parseRouteFrom(tab.getAttribute("href"));
    if (target === route.name) tab.setAttribute("aria-current", "page");
    else tab.removeAttribute("aria-current");
  }
}

function parseRouteFrom(href) {
  const name = (href || "#/").slice(2).split("/")[0];
  return name || "overview";
}

/* ----------------------------------------------------- events & interaction */

const tooltip = () => $("#tooltip");

function showTooltip(payload, event) {
  const node = tooltip();
  node.innerHTML = `<div class="tooltip__title">${esc(payload.title)}</div>
    <dl>${payload.rows
      .map(([label, value]) => `<dt>${esc(label)}</dt><dd>${esc(value)}</dd>`)
      .join("")}</dl>`;
  node.dataset.open = "true";
  moveTooltip(event);
}

function moveTooltip(event) {
  const node = tooltip();
  const box = node.getBoundingClientRect();
  const x = Math.min(event.clientX + 14, window.innerWidth - box.width - 12);
  const y = Math.min(event.clientY + 14, window.innerHeight - box.height - 12);
  node.style.left = `${Math.max(8, x)}px`;
  node.style.top = `${Math.max(8, y)}px`;
}

function hideTooltip() {
  tooltip().dataset.open = "false";
}

/**
 * Where a card sits in this meta, for the inspector.
 *
 * The inspector used to show the printing and nothing else: cost, type, stats, rules
 * text - everything you could read off the card itself, and none of what the report
 * knows. You would click a card while deciding whether to tech against it and learn
 * only what it does, never how much of the field runs it or whether that is growing.
 *
 * Returns null for a card outside the threat board (it lists the top 150), because
 * saying nothing is better than implying it is played by nobody.
 */
function cardPosition(name) {
  // Keyed by the report object, not just cached: a lookup that outlives the meta it
  // was built from answers with the previous report's numbers, and nothing about the
  // answer would look wrong.
  if (!state.threatIndex || state.threatIndex.meta !== state.meta) {
    state.threatIndex = {
      meta: state.meta,
      byName: new Map(state.meta.threats.map((threat) => [threat.name, threat])),
    };
  }
  return state.threatIndex.byName.get(name) || null;
}

/**
 * The inspector's markup for one card, or null if the report does not describe it.
 *
 * Split out from `showCard` so it can be tested without a DOM: what matters is what
 * the panel says, and a test that stubs `getElementById` to capture an assignment is
 * testing the plumbing instead.
 */
function inspectCard(name) {
  const info = state.meta.cards[name];
  if (!info) return null;
  const badges = [
    info.cost !== null ? `${info.cost} ink` : "",
    info.type,
    info.inkable ? "inkable" : "uninkable",
    info.lore !== null && info.lore !== undefined ? `${info.lore} lore` : "",
    info.strength !== null && info.willpower !== null && info.strength !== undefined
      ? `${info.strength}/${info.willpower}`
      : "",
    info.rarity,
  ].filter(Boolean);

  const position = cardPosition(name);
  const meta = !position
    ? `<p class="subtitle">Outside the top ${num(
        state.meta.threats.length
      )} cards of this field, so the report holds no field figures for it.</p>`
    : `<div class="table-wrap"><table><tbody>
        <tr><td>Chance you meet it</td><td class="num">${pct(
          position.field_presence,
          0
        )}</td></tr>
        <tr><td>Decks running it</td><td class="num">${num(position.decks)} of ${num(
          state.meta.totals.decks
        )}</td></tr>
        <tr><td>When you do</td><td class="num"><b>${num(
          position.typical_copies
        )}×</b></td></tr>
        <tr><td>Expected copies</td><td class="num">${num(
          position.expected_copies,
          2
        )}</td></tr>
        ${
          state.meta.trend.usable
            ? `<tr><td>Movement</td><td class="num">${deltaText(position.trend)}</td></tr>`
            : ""
        }
      </tbody></table></div>
      <p class="subtitle" style="margin-top:10px">Played by</p>
      <div class="inspector__meta">${position.archetypes
        .map((group) =>
          group.is_brews
            ? `<span class="badge">${esc(group.label)} ${pct(group.inclusion, 0)}</span>`
            : `<a class="badge" href="#/pair/${esc(group.pair)}">${esc(group.label)} ${pct(
                group.inclusion,
                0
              )}</a>`
        )
        .join("")}</div>`;

  return `
    ${
      info.image
        ? `<img src="${esc(info.image)}" alt="${esc(name)}" loading="lazy" />`
        : ""
    }
    <div class="card__head" style="margin-top:10px"><h2>${esc(name)}</h2></div>
    <div class="inspector__meta">${badges
      .map((b) => `<span class="badge">${esc(b)}</span>`)
      .join("")}</div>
    ${info.text ? `<div class="inspector__text">${esc(info.text)}</div>` : ""}
    ${meta}`;
}

function showCard(name) {
  const body = inspectCard(name);
  if (body === null) return;
  $("#inspector-body").innerHTML = body;
  $("#inspector").hidden = false;
}

function attachEvents() {
  window.addEventListener("hashchange", () => {
    state.route = parseRoute();
    state.cardFilter = "";
    state.typeFilter = "";
    state.showFringe = false;
    render();
    window.scrollTo({ top: 0 });
  });

  const view = $("#view");

  view.addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-table-toggle]");
    if (toggle) {
      const id = toggle.dataset.tableToggle;
      state.tables.has(id) ? state.tables.delete(id) : state.tables.add(id);
      render();
      return;
    }
    const card = event.target.closest("[data-card]");
    if (card) {
      showCard(card.dataset.card);
    }
  });

  view.addEventListener("input", (event) => {
    if (event.target.id === "card-search") {
      state.cardFilter = event.target.value;
      const caret = event.target.selectionStart;
      render();
      const field = $("#card-search");
      if (field) {
        field.focus();
        field.setSelectionRange(caret, caret);
      }
    }
  });

  view.addEventListener("change", (event) => {
    if (event.target.id === "type-filter") {
      state.typeFilter = event.target.value;
      render();
    }
    if (event.target.id === "fringe-toggle") {
      state.showFringe = event.target.checked;
      render();
    }
    if (event.target.id === "threat-sort") {
      state.threatSort = event.target.value;
      render();
    }
  });

  // Hover layer: any mark carrying data-tip gets a tooltip, keyboard focus included.
  for (const type of ["mouseover", "focusin"]) {
    view.addEventListener(type, (event) => {
      const mark = event.target.closest("[data-tip]");
      if (mark) showTooltip(JSON.parse(mark.dataset.tip), event.clientX ? event : fakeEvent(mark));
    });
  }
  view.addEventListener("mousemove", (event) => {
    if (tooltip().dataset.open === "true" && event.target.closest("[data-tip]")) {
      moveTooltip(event);
    }
  });
  for (const type of ["mouseout", "focusout"]) {
    view.addEventListener(type, (event) => {
      if (event.target.closest("[data-tip]")) hideTooltip();
    });
  }

  $("#inspector-close").addEventListener("click", () => {
    $("#inspector").hidden = true;
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      $("#inspector").hidden = true;
      hideTooltip();
    }
  });

  const toggle = $("#theme-toggle");
  toggle.addEventListener("click", () => {
    const current =
      document.documentElement.dataset.theme ||
      (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("lorcana-meta-theme", next);
    } catch (error) {
      /* private browsing - the OS preference still applies */
    }
  });
}

function fakeEvent(node) {
  const box = node.getBoundingClientRect();
  return { clientX: box.right, clientY: box.top };
}

function restoreTheme() {
  try {
    const saved = localStorage.getItem("lorcana-meta-theme");
    if (saved === "dark" || saved === "light") document.documentElement.dataset.theme = saved;
  } catch (error) {
    /* nothing stored is a fine state */
  }
}

/**
 * Read the report.
 *
 * A bundled single-file report (tools/bundle_report.py) carries the data inline,
 * because a page opened from the filesystem cannot fetch a sibling file - browsers
 * block that on file://. When the tag is absent we are being served over HTTP and
 * fetch the JSON as normal.
 */
/**
 * Fill in blocks a report built by an older version does not have.
 *
 * A `meta.json` left on disk from a previous build is a normal thing to open, and
 * several places read `meta.trend.usable` without asking first. A missing block would
 * throw during render and leave a blank page - the one failure mode with no clue in
 * it. Defaulting to "not shown, and here is why" degrades to the state the page
 * already knows how to draw.
 */
function withDefaults(meta) {
  if (!meta.trend) {
    meta.trend = {
      usable: false,
      reason: "this report was built before movement existed - rebuild it to see it",
      split: "",
      first: { start: "", end: "", decks: 0 },
      second: { start: "", end: "", decks: 0 },
      undated_decks: 0,
      min_decks_per_row: 0,
    };
  }
  return meta;
}

async function loadMeta() {
  const inline = document.getElementById("meta-data");
  if (inline) return withDefaults(JSON.parse(inline.textContent));

  const response = await fetch(DATA_URL, { cache: "no-cache" });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return withDefaults(await response.json());
}

async function boot() {
  restoreTheme();
  state.route = parseRoute();
  attachEvents();
  try {
    state.meta = await loadMeta();
  } catch (error) {
    $("#view").innerHTML = `<div class="empty">
        <p>No report data yet.</p>
        <p class="hint">
          The report data is generated, not committed, so a fresh clone starts empty.
          Build it with
          <code>python tools/generate_sample_decks.py</code> then
          <code>lorcana-meta build --source local --last 40</code>.
        </p>
        <p class="hint">Could not load <code>${DATA_URL}</code>: ${esc(error.message)}</p>
      </div>`;
    return;
  }
  render();
}

// Guarded so the file can be evaluated outside a browser. `tests/test_render.mjs`
// loads this exact source and calls the renderers directly; without the guard it
// would have to cut the call out with a regex, and a test that edits the code it
// tests is testing something else.
if (typeof document !== "undefined") boot();
