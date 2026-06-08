// AC→source map (Dispatch port-back 2026-06-02 / epic-overlap):
//   extractEpicFiles(backlogPath) → Map<epicKey, Set<filePath>>
//     - epic heading: ### Epic <id>: <name>
//     - files come from `* **Files:**` blocks; path is first backtick-delimited token
//   findOverlaps(map) → [{epicA, epicB, sharedFiles}] — each pair once, epicA<epicB, files sorted
//   read failure → throw with path in message

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createRequire } from 'node:module';
import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs';

const require = createRequire(import.meta.url);
const { extractEpicFiles, extractEpicPhases, findOverlaps } = require('../epic-overlap');

let dir;
beforeEach(() => {
    dir = fs.mkdtempSync(path.join(os.tmpdir(), 'epic-overlap-'));
});
afterEach(() => {
    fs.rmSync(dir, { recursive: true, force: true });
});

function writeBacklog(body) {
    const p = path.join(dir, '_backlog.md');
    fs.writeFileSync(p, body);
    return p;
}

const BACKLOG = `# Backlog

### Epic 1: Authentication

#### Story 1.1: Login
* **Files:**
  * \`src/auth/login.ts\` — new
  * \`src/shared/db.ts\` — modified

### Epic 2: Billing

#### Story 2.1: Checkout
* **Files:**
  * \`src/billing/checkout.ts\` — new
  * \`src/shared/db.ts\` — modified

### Epic 3: Docs

#### Story 3.1: README
* **Files:**
  * \`README.md\` — modified
`;

describe('extractEpicFiles', () => {
    it('maps each epic heading to the set of files its stories claim', () => {
        const map = extractEpicFiles(writeBacklog(BACKLOG));
        expect([...map.keys()]).toEqual([
            'Epic 1: Authentication',
            'Epic 2: Billing',
            'Epic 3: Docs',
        ]);
        expect([...map.get('Epic 1: Authentication')]).toEqual(['src/auth/login.ts', 'src/shared/db.ts']);
        expect([...map.get('Epic 3: Docs')]).toEqual(['README.md']);
    });

    it('keeps only the path inside the first backticks, dropping the description', () => {
        const map = extractEpicFiles(writeBacklog(BACKLOG));
        expect(map.get('Epic 2: Billing').has('src/billing/checkout.ts')).toBe(true);
    });

    it('throws with the path when the file cannot be read', () => {
        expect(() => extractEpicFiles(path.join(dir, 'nope.md'))).toThrow(/nope\.md/);
    });
});

describe('findOverlaps', () => {
    it('reports each sharing pair once with sorted shared files, epicA<epicB', () => {
        const map = extractEpicFiles(writeBacklog(BACKLOG));
        const overlaps = findOverlaps(map);
        expect(overlaps).toEqual([
            { epicA: 'Epic 1: Authentication', epicB: 'Epic 2: Billing', sharedFiles: ['src/shared/db.ts'] },
        ]);
    });

    it('returns an empty array when no epics share files', () => {
        const map = new Map([
            ['Epic 1: A', new Set(['a.ts'])],
            ['Epic 2: B', new Set(['b.ts'])],
        ]);
        expect(findOverlaps(map)).toEqual([]);
    });
});

// ── F6: phase-aware overlap ────────────────────────────────────────────────
describe('extractEpicPhases', () => {
    it('mapsEachEpicToItsPhaseHeading', () => {
        const p = path.join(dir, 'b.md');
        fs.writeFileSync(p, [
            '## Phase 0: Foundation',
            '### Epic 0: Tooling',
            '## Phase 1: Core',
            '### Epic 1: Engine',
            '### Epic 2: Persistence',
        ].join('\n'));
        const phases = extractEpicPhases(p);
        expect(phases.get('Epic 0: Tooling')).toBe('Phase 0: Foundation');
        expect(phases.get('Epic 1: Engine')).toBe('Phase 1: Core');
        expect(phases.get('Epic 2: Persistence')).toBe('Phase 1: Core');
    });

    it('epicBeforeAnyPhase_mapsToNull', () => {
        const p = path.join(dir, 'c.md');
        fs.writeFileSync(p, '### Epic 9: Loose\n');
        expect(extractEpicPhases(p).get('Epic 9: Loose')).toBe(null);
    });
});

describe('findOverlaps — phase awareness (F6)', () => {
    const map = new Map([
        ['Epic 1: A', new Set(['shared.ts'])],
        ['Epic 2: B', new Set(['shared.ts'])],
    ]);

    it('crossPhaseOverlap_taggedSamePhaseFalse', () => {
        const phases = new Map([['Epic 1: A', 'Phase 0: X'], ['Epic 2: B', 'Phase 1: Y']]);
        const [o] = findOverlaps(map, phases);
        expect(o.sharedFiles).toEqual(['shared.ts']);
        expect(o.samePhase).toBe(false); // different phases → cannot collide in a wave
    });

    it('samePhaseOverlap_taggedSamePhaseTrue', () => {
        const phases = new Map([['Epic 1: A', 'Phase 0: X'], ['Epic 2: B', 'Phase 0: X']]);
        expect(findOverlaps(map, phases)[0].samePhase).toBe(true);
    });

    it('unknownPhase_conservativelyGates_samePhaseTrue', () => {
        const phases = new Map([['Epic 1: A', 'Phase 0: X']]); // Epic 2 phase unknown
        expect(findOverlaps(map, phases)[0].samePhase).toBe(true);
    });

    it('withoutPhaseMap_omitsSamePhaseField_backwardCompatible', () => {
        const [o] = findOverlaps(map);
        expect(o).not.toHaveProperty('samePhase');
    });
});
