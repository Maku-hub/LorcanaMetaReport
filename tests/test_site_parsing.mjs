/* The site parses a pasted decklist in the browser, and the pipeline parses the
 * same lists in Python. If the two drift, a player's list stops matching the meta
 * and nothing visibly breaks - so pin the browser half here.
 *
 *   node tests/test_site_parsing.mjs
 *
 * The two pure functions are lifted out of app.js by name rather than imported,
 * because app.js is a plain script that boots itself against a real DOM.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const source = readFileSync(join(root, "site/assets/app.js"), "utf8");

function lift(name) {
  const start = source.indexOf(`function ${name}(`);
  if (start === -1) throw new Error(`${name}() is gone from app.js - update this test`);
  let depth = 0;
  for (let i = source.indexOf("{", start); i < source.length; i++) {
    if (source[i] === "{") depth++;
    else if (source[i] === "}" && --depth === 0) {
      return source.slice(start, i + 1);
    }
  }
  throw new Error(`could not find the end of ${name}()`);
}

const { normalizeName, parsePastedDeck } = new Function(
  `${lift("normalizeName")}\n${lift("parsePastedDeck")}\nreturn { normalizeName, parsePastedDeck };`
)();

const failures = [];
const check = (condition, message) => {
  if (!condition) failures.push(message);
};

/* -------------------------------------------------------------- normalisation */

check(normalizeName("Elsa - Snow Queen") === "elsa snow queen", "plain hyphen");
check(normalizeName("Elsa – Snow Queen") === "elsa snow queen", "en dash folds");
check(normalizeName("Café Life") === "cafe life", "accents fold");
check(
  normalizeName("Let’s Get Down to Business") === normalizeName("Let's Get Down to Business"),
  "curly and straight apostrophes agree"
);
check(normalizeName("  MICKEY   MOUSE  ") === "mickey mouse", "case and spacing fold");

/* ----------------------------------------------------------- paste parsing */

const pasted = parsePastedDeck(`Characters (3)
4 Elsa - Snow Queen
3x Hades - Lord of the Underworld
2 Mickey Mouse - Brave Little Tailor (TFC) 42

Songs (1)
1 Be Prepared #57
Grab Your Sword x2
`);

const expected = {
  "elsa snow queen": 4,
  "hades lord of the underworld": 3,
  "mickey mouse brave little tailor": 2,
  "be prepared": 1,
  "grab your sword": 2,
};

for (const [key, count] of Object.entries(expected)) {
  check(pasted.get(key) === count, `${key} -> ${count}, got ${pasted.get(key)}`);
}
check(pasted.size === 5, `headers skipped, got ${[...pasted.keys()].join(", ")}`);

/* Duplicated lines add up rather than overwrite - some exports split by section. */
const doubled = parsePastedDeck("2 Elsa - Snow Queen\n2 Elsa - Snow Queen");
check(doubled.get("elsa snow queen") === 4, `duplicate lines sum, got ${doubled.get("elsa snow queen")}`);

/* Noise stays out. */
const noise = parsePastedDeck("Total: 60\n99 Nonsense Card\nab\n");
check(noise.size === 0, `noise rejected, got ${[...noise.keys()].join(", ")}`);

/* ------------------------------------------------------------------ report */

if (failures.length) {
  console.error(`${failures.length} failure(s):`);
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log("site parsing matches the pipeline");
